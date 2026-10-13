import atexit
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from leadagent import notify
from leadagent.agent.prompts import system_prompt
from leadagent.agent.tools import TOOLS
from leadagent.settings import get_settings
from leadagent.store import repo
from leadagent.store.db import session_scope
from leadagent.store.models import utcnow

LIMIT = 40  # user messages per lead per rolling 24 hours
HISTORY = 20  # messages sent to the model
# shortcut: canned replies are English only, translate per user language when an institute asks
NONTEXT_REPLY = "Please type your question as a text message."
LIMIT_REPLY = "Thank you for your messages. Our team will contact you soon."


class State(MessagesState):
    kind: str  # "text" or "other"
    route: str  # "agent", "relay" or "canned"
    reply: str  # text for the canned route, otherwise ""


def thread_config(institute_id, lead_id) -> dict:
    return {"configurable": {"thread_id": str(lead_id), "institute_id": institute_id, "lead_id": lead_id}}


def message_text(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    )


def drop_dangling_tool_calls(messages):
    """Remove tool calls that never got a result, and results whose call is gone.

    A run that fails between the model's tool call and the tool's result leaves such a pair in the saved
    state, and the model API rejects any history that contains one.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    kept = [
        m
        for m in messages
        if not (isinstance(m, AIMessage) and m.tool_calls and not all(c["id"] in answered for c in m.tool_calls))
    ]
    called = {c["id"] for m in kept if isinstance(m, AIMessage) for c in m.tool_calls}
    return [m for m in kept if not isinstance(m, ToolMessage) or m.tool_call_id in called]


def gate(state: State, config: RunnableConfig) -> dict:
    ids = config["configurable"]
    with session_scope() as session:
        lead = repo.get_lead(session, ids["institute_id"], ids["lead_id"])
        if lead is None:
            return {"route": "canned", "reply": ""}
        if lead.stage == "handed_off":
            return {"route": "relay", "reply": ""}
        if state["kind"] != "text":
            return {"route": "canned", "reply": NONTEXT_REPLY}
        if repo.user_messages_last_24h(session, lead.id, utcnow()) > LIMIT:
            repo.hand_off(session, lead, "daily message limit reached")
            institute = repo.get_institute(session, lead.institute_id)
            notify.alert(
                institute,
                f"⚠️ Lead #{lead.id} sent more than {LIMIT} messages in 24 hours. The assistant has stopped "
                f"replying to them.\n{notify.describe(lead)}\nSend /resume {lead.id} to switch it back on.",
            )
            return {"route": "canned", "reply": LIMIT_REPLY}
    return {"route": "agent", "reply": ""}


def relay(state: State, config: RunnableConfig) -> dict:
    # shortcut: every message from a handed-off lead is forwarded, batch them if an owner reports spam
    ids = config["configurable"]
    with session_scope() as session:
        lead = repo.get_lead(session, ids["institute_id"], ids["lead_id"])
        institute = repo.get_institute(session, ids["institute_id"])
        if lead is not None:
            notify.alert(
                institute,
                f"💬 Lead #{lead.id} ({lead.name or 'no name'}) wrote:\n{message_text(state['messages'][-1])}",
            )
    return {}


def make_agent(model, cache_prompt):
    def agent(state: State, config: RunnableConfig) -> dict:
        with session_scope() as session:
            prompt = system_prompt(repo.get_institute(session, config["configurable"]["institute_id"]))
        history = trim_messages(
            drop_dangling_tool_calls(state["messages"]),
            strategy="last",
            token_counter=len,  # counts messages, not tokens
            max_tokens=HISTORY,
            start_on="human",
            include_system=False,
        )
        if cache_prompt:
            system = SystemMessage(content=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}])
        else:
            system = SystemMessage(content=prompt)
        return {"messages": [model.invoke([system, *history], config)]}

    return agent


def build_graph(model, checkpointer, cache_prompt=True):
    builder = StateGraph(State)
    builder.add_node("gate", gate)
    builder.add_node("relay", relay)
    builder.add_node("agent", make_agent(model, cache_prompt))
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_edge(START, "gate")
    builder.add_conditional_edges("gate", lambda state: state["route"], {"relay": "relay", "canned": END, "agent": "agent"})
    builder.add_edge("relay", END)
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


@lru_cache
def get_checkpointer() -> PostgresSaver:
    pool = ConnectionPool(
        conninfo=get_settings().database_url,
        max_size=5,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    atexit.register(pool.close)  # without this the pool's worker threads delay interpreter exit
    saver = PostgresSaver(pool)
    saver.setup()
    return saver


def _chat(max_tokens) -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        max_tokens=max_tokens,
        timeout=30,
        max_retries=2,
    )


@lru_cache
def get_plain_model():
    return _chat(200)


@lru_cache
def get_graph():
    return build_graph(_chat(500).bind_tools(TOOLS), get_checkpointer())
