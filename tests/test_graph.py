from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from helpers import ScriptedModel, make_institute, make_lead, run_turn, tool_call
from leadagent.agent.graph import (
    LIMIT,
    NONTEXT_REPLY,
    WAITING_REPLY,
    build_graph,
    drop_dangling_tool_calls,
    get_checkpointer,
    make_agent,
    message_text,
    thread_config,
)
from leadagent.store import repo
from leadagent.store.models import utcnow


def graph_with(*replies):
    model = ScriptedModel(*replies)
    return build_graph(model, get_checkpointer()), model


def test_a_plain_reply(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    graph, model = graph_with(AIMessage("The JEE fee is ₹68,000 per year."))
    result = run_turn(graph, lead, "JEE fee?")
    assert result["route"] == "agent"
    assert message_text(result["messages"][-1]) == "The JEE fee is ₹68,000 per year."
    system, human = model.calls[0]
    assert isinstance(system, SystemMessage)
    assert "₹68,000 per year" in system.content[0]["text"]
    assert system.content[0]["cache_control"] == {"type": "ephemeral"}
    assert human.content == "JEE fee?"


def test_system_prompt_is_a_plain_string_when_caching_is_off(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("ok"))
    graph = build_graph(model, get_checkpointer(), cache_prompt=False)
    run_turn(graph, lead, "hi")
    assert isinstance(model.calls[0][0].content, str)


def test_a_tool_call_saves_the_lead_then_replies(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    graph, model = graph_with(tool_call("save_lead", name="Rahul"), AIMessage("Thanks Rahul! Which class?"))
    result = run_turn(graph, lead, "I am Rahul")
    session.refresh(lead)
    assert lead.name == "Rahul"
    assert message_text(result["messages"][-1]) == "Thanks Rahul! Which class?"
    assert isinstance(model.calls[1][-1], ToolMessage)


def test_conversation_state_survives_between_turns(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    graph, model = graph_with(AIMessage("Hello!"), AIMessage("Class 11 noted."))
    run_turn(graph, lead, "hi")
    run_turn(graph, lead, "class 11")
    assert [m.content for m in model.calls[1][1:]] == ["hi", "Hello!", "class 11"]


def test_after_handoff_the_bot_acknowledges_and_relays_to_the_owner(session, sent):
    lead = make_lead(session, make_institute(session), stage="collecting", name="Rahul")
    graph, model = graph_with(tool_call("handoff", reason="asked for a person"), AIMessage("Our team will contact you."))
    run_turn(graph, lead, "I want to talk to sir")
    sent.clear()
    result = run_turn(graph, lead, "hello? anyone?")
    assert (result["route"], result["reply"]) == ("relay", WAITING_REPLY)
    assert len(model.calls) == 2  # the model was not called for the second message
    assert sent == [("telegram", lead.institute_id, "999", f"💬 Lead #{lead.id} (Rahul) wrote:\nhello? anyone?")]


def test_a_non_text_message_gets_the_canned_reply(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    graph, model = graph_with()
    result = run_turn(graph, lead, "[non-text message]", kind="other")
    assert (result["route"], result["reply"]) == ("canned", NONTEXT_REPLY)
    assert model.calls == []


def test_exactly_at_the_limit_is_still_answered(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    for i in range(LIMIT):
        repo.log_message(session, lead, "user", "x", f"tg:{i}")
    session.commit()
    graph, _ = graph_with(AIMessage("ok"))
    assert run_turn(graph, lead, "x")["route"] == "agent"


def test_only_the_last_20_messages_reach_the_model(session):
    institute = make_institute(session)
    lead = make_lead(session, institute, stage="collecting")
    model = ScriptedModel(AIMessage("ok"))
    history = []
    for i in range(30):
        history += [HumanMessage(f"q{i}"), AIMessage(f"a{i}")]
    make_agent(model, cache_prompt=True)({"messages": history}, thread_config(institute.id, lead.id))
    sent_to_model = model.calls[0]
    assert len(sent_to_model) == 21  # system prompt + 20
    assert isinstance(sent_to_model[1], HumanMessage)
    assert sent_to_model[-1].content == "a29"


def test_dangling_tool_calls_are_dropped():
    answered = tool_call("save_lead", name="A")
    dangling = AIMessage(content="", tool_calls=[{"name": "handoff", "args": {}, "id": "call_lost", "type": "tool_call"}])
    orphan = ToolMessage("x", tool_call_id="call_nobody")
    messages = [
        HumanMessage("hi"),
        answered,
        ToolMessage("Saved.", tool_call_id="call_save_lead"),
        AIMessage("ok"),
        HumanMessage("again"),
        dangling,
        orphan,
        HumanMessage("hello?"),
    ]
    kept = drop_dangling_tool_calls(messages)
    assert dangling not in kept and orphan not in kept
    assert len(kept) == 6


def test_a_lead_is_not_stuck_after_a_tool_step_fails(session, monkeypatch):
    lead = make_lead(session, make_institute(session), stage="collecting")
    # Three replies: whether the tool node raises the error or reports it to the model depends on the
    # LangGraph version, and the first turn uses one reply more in the second case.
    graph, model = graph_with(tool_call("save_lead", name="Rahul"), AIMessage("Hello again!"), AIMessage("Hello again!"))

    def broken(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr("leadagent.agent.tools.repo.save_lead_fields", broken)
    try:
        run_turn(graph, lead, "I am Rahul")
    except Exception:
        pass
    monkeypatch.undo()
    result = run_turn(graph, lead, "hello?")
    assert message_text(result["messages"][-1]) == "Hello again!"
    # Every tool call the model is shown must have its result, or the model API rejects the request.
    last_call = model.calls[-1]
    answered = {m.tool_call_id for m in last_call if isinstance(m, ToolMessage)}
    for message in last_call:
        for call in getattr(message, "tool_calls", None) or []:
            assert call["id"] in answered


def test_message_text_reads_strings_and_content_blocks():
    assert message_text(AIMessage("plain")) == "plain"
    blocks = AIMessage(content=[{"type": "text", "text": "a"}, {"type": "tool_use", "id": "1", "name": "x", "input": {}}, {"type": "text", "text": "b"}])
    assert message_text(blocks) == "ab"


def test_a_reply_in_the_wrong_script_is_rewritten_once(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("Yes, there is a bus from Sector 19."), AIMessage("हाँ, सेक्टर 19 से बस है।"))
    result = run_turn(build_graph(model, get_checkpointer()), lead, "क्या सेक्टर 19 से बस है?")
    assert message_text(result["messages"][-1]) == "हाँ, सेक्टर 19 से बस है।"
    assert len(model.calls) == 2
    assert "Devanagari" in model.calls[1][-1].content


def test_a_reply_in_the_right_script_is_not_rewritten(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("The fee is 68,000 rupees a year."))
    run_turn(build_graph(model, get_checkpointer()), lead, "What is the fee?")
    assert len(model.calls) == 1


def test_a_failed_rewrite_keeps_the_original_reply(session):
    lead = make_lead(session, make_institute(session), stage="collecting")
    model = ScriptedModel(AIMessage("Yes, there is a bus."), AIMessage(""))
    result = run_turn(build_graph(model, get_checkpointer()), lead, "क्या बस है?")
    assert message_text(result["messages"][-1]) == "Yes, there is a bus."
