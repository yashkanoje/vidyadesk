from contextlib import contextmanager
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from leadagent import notify
from leadagent.rag.search import search
from leadagent.store import repo
from leadagent.store.db import session_scope

GONE = "This lead no longer exists."
NOTHING_FOUND = "Nothing found in the institute's documents."


@contextmanager
def _current(config):
    """Yield (session, institute, lead) for this conversation. The ids come from the run config, never from the model."""
    ids = config["configurable"]
    with session_scope() as session:
        institute = repo.get_institute(session, ids["institute_id"])
        lead = repo.get_lead(session, ids["institute_id"], ids["lead_id"])
        yield session, institute, lead


@tool
def save_lead(
    config: RunnableConfig,
    name: str = "",
    student_class: str = "",
    course: str = "",
    phone: str = "",
    notes: str = "",
) -> str:
    """Save details the user has given about the student. Pass only the fields you just learned and leave the rest empty. Call this as soon as you learn any detail."""
    with _current(config) as (session, _, lead):
        if lead is None:
            return GONE
        repo.save_lead_fields(session, lead, name=name, student_class=student_class, course=course, phone=phone, notes=notes)
        missing = [
            label
            for label, value in (("name", lead.name), ("class", lead.student_class), ("course", lead.course))
            if not value
        ]
    return f"Saved. Still needed: {', '.join(missing)}." if missing else "Saved. All details captured."


@tool
def set_interest(config: RunnableConfig, level: Literal["hot", "warm", "cold"], reason: str) -> str:
    """Record how likely this lead is to join. hot: asks about admission, payment, a demo class or a joining date. cold: says they are not interested. warm: anything else."""
    with _current(config) as (session, institute, lead):
        if lead is None:
            return GONE
        was_hot = lead.interest == "hot"
        repo.set_interest(session, lead, level, reason)
        if level == "hot" and not was_hot:
            notify.alert(institute, f"🔥 Hot lead #{lead.id}\n\n{notify.describe(lead)}\nWhy: {notify.flat(reason)}")
    return f"Interest recorded as {level}."


@tool
def handoff(config: RunnableConfig, reason: str) -> str:
    """Hand this conversation to the institute's human team. Use it when the user asks for a person, is upset, or asks something the institute information does not answer."""
    with _current(config) as (session, institute, lead):
        if lead is None:
            return GONE
        repo.hand_off(session, lead, reason)
        notify.alert(
            institute,
            f"🙋 Handoff: lead #{lead.id}\n\n{notify.describe(lead)}\nWhy: {notify.flat(reason)}\n\n"
            f"Send /resume {lead.id} to switch the assistant back on.",
        )
    return "Handed off. Tell the user that the institute's team will contact them soon."


@tool
def search_docs(config: RunnableConfig, query: str) -> str:
    """Search the institute's documents (prospectus, brochures, rules) for anything the institute information above does not answer. Write the query in English, whatever language the user wrote in."""
    with session_scope() as session:
        passages = search(session, config["configurable"]["institute_id"], query)
    if not passages:
        return NOTHING_FOUND
    return "\n\n".join(f"Passage {i} (from {p.document}):\n{p.text}" for i, p in enumerate(passages, 1))


TOOLS = [save_lead, set_interest, handoff, search_docs]
