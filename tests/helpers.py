import hashlib
import math
import re

from langchain_core.messages import AIMessage, HumanMessage
from leadagent.crypto import encrypt
from leadagent.store.models import Institute, Lead


FACTS = {
    "institute_name": "BrightPath Classes",
    "address": "Plot 12, Civil Township, Rourkela, Odisha 769004",
    "phone": "0661-2400000",
    "timings": "Monday to Saturday, 9 am to 8 pm",
    "courses": [
        {
            "name": "JEE Main + Advanced",
            "for_classes": "Class 11 and 12",
            "fee": "₹68,000 per year",
            "batches": ["Mon to Sat 6 am to 8 am", "Mon to Sat 5 pm to 7:30 pm"],
        },
        {
            "name": "NEET",
            "for_classes": "Class 11 and 12",
            "fee": "₹62,000 per year",
            "batches": ["Mon to Sat 4 pm to 6:30 pm"],
        },
    ],
    "faq": [{"q": "Is there a demo class?", "a": "Yes, the first two classes are free."}],
}




def make_institute(session, slug="bright", owner_chat_id="999", whatsapp_phone_number_id=None, active=True):
    institute = Institute(
        slug=slug,
        name=slug.title() + " Classes",
        active=active,
        facts=FACTS,
        telegram_bot_token_enc=encrypt(f"token-{slug}"),
        telegram_secret=f"secret-{slug}",
        owner_telegram_chat_id=owner_chat_id,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_token_enc=encrypt("wa-token") if whatsapp_phone_number_id else None,
    )
    session.add(institute)
    session.commit()
    return institute


def make_lead(session, institute, user_id="111", channel="telegram", **fields):
    lead = Lead(institute_id=institute.id, channel=channel, channel_user_id=user_id, **fields)
    session.add(lead)
    session.commit()
    return lead




class ScriptedModel:
    """Stands in for the chat model: returns the given replies in order and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages, config=None):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def tool_call(tool, /, **args):
    # "tool" is positional-only so that a tool argument may itself be called "name"
    return AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": f"call_{tool}", "type": "tool_call"}])


def run_turn(graph, lead, text, kind="text"):
    from leadagent.agent.graph import thread_config

    return graph.invoke(
        {"messages": [HumanMessage(text)], "kind": kind},
        thread_config(lead.institute_id, lead.id),
    )


class FakeEmbedder:
    """Stands in for the real model: texts that share words get similar vectors. Deterministic and instant."""

    dims = 384

    def _vector(self, text):
        vector = [0.0] * self.dims
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dims] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]

    def passages(self, texts):
        return [self._vector(text) for text in texts]

    def query(self, text):
        return self._vector(text)
