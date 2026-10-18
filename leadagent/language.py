"""Which writing system a text uses, so the agent's reply can match the user's."""


def script_of(text) -> str:
    counts = {
        "odia": sum("଀" <= ch <= "୿" for ch in text),
        "devanagari": sum("ऀ" <= ch <= "ॿ" for ch in text),
        "latin": sum(ch.isascii() and ch.isalpha() for ch in text),
    }
    if not any(counts.values()):
        return "none"
    # A reply that mixes native script with English words (course names) counts as the native script.
    for script in ("odia", "devanagari"):
        if counts[script] >= 5:
            return script
    return max(counts, key=counts.get)


REWRITE_INSTRUCTION = {
    "devanagari": "Rewrite your last reply in Devanagari script, in the user's language. Keep the same meaning and facts. Reply with the rewritten message only.",
    "odia": "Rewrite your last reply in Odia script (ଓଡ଼ିଆ). Keep the same meaning and facts. Reply with the rewritten message only.",
    "latin": "Rewrite your last reply using English letters only, in the same language the user wrote in (for example Hinglish, or Odia written in English letters). Keep the same meaning and facts. Reply with the rewritten message only.",
}


def rewrite_script(user_text, reply_text):
    """The script the reply must be rewritten into, or None when it already matches the user's."""
    wanted, got = script_of(user_text), script_of(reply_text)
    if wanted == "none" or got == "none" or wanted == got:
        return None
    return wanted
