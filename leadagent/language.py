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


# Fixed replies in Hindi and Odia, keyed by the English text. Written without a native speaker's check (Odia most of all).
TRANSLATIONS = {
    "Please type your question as a text message.": {
        "devanagari": "कृपया अपना सवाल टेक्स्ट मैसेज में लिखकर भेजें।",
        "odia": "ଦୟାକରି ଆପଣଙ୍କ ପ୍ରଶ୍ନ ଟେକ୍ସଟ୍ ମେସେଜରେ ଲେଖି ପଠାନ୍ତୁ।",
    },
    "Thank you for your messages. Our team will contact you soon.": {
        "devanagari": "आपके संदेशों के लिए धन्यवाद। हमारी टीम जल्द ही आपसे संपर्क करेगी।",
        "odia": "ଆପଣଙ୍କ ମେସେଜ ପାଇଁ ଧନ୍ୟବାଦ। ଆମ ଟିମ୍ ଶୀଘ୍ର ଆପଣଙ୍କ ସହ ଯୋଗାଯୋଗ କରିବେ।",
    },
    "Our team has your message and will reply soon.": {
        "devanagari": "आपका संदेश हमारी टीम तक पहुँच गया है, वे जल्द ही जवाब देंगे।",
        "odia": "ଆପଣଙ୍କ ମେସେଜ ଆମ ଟିମ୍ ପାଖରେ ପହଞ୍ଚିଛି, ସେମାନେ ଶୀଘ୍ର ଉତ୍ତର ଦେବେ।",
    },
    "We'll get back to you shortly.": {
        "devanagari": "हम जल्द ही आपसे संपर्क करेंगे।",
        "odia": "ଆମେ ଶୀଘ୍ର ଆପଣଙ୍କ ସହ ଯୋଗାଯୋଗ କରିବୁ।",
    },
}


def in_users_script(english, user_text) -> str:
    """A fixed reply in the script the user writes in; English for Latin letters (Hinglish too) or no text."""
    return TRANSLATIONS.get(english, {}).get(script_of(user_text or ""), english)


def all_versions(english) -> list[str]:
    return [english, *TRANSLATIONS.get(english, {}).values()]


def rewrite_script(user_text, reply_text):
    """The script the reply must be rewritten into, or None when it already matches the user's."""
    wanted, got = script_of(user_text), script_of(reply_text)
    if wanted == "none" or got == "none" or wanted == got:
        return None
    return wanted
