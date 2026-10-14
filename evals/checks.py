import re

_NUMBER = re.compile(r"\d[\d,]*\d|\d")  # \d also matches Devanagari and Odia digits


def numbers_in(text) -> set[int]:
    return {int(match.replace(",", "")) for match in _NUMBER.findall(text)}  # int() reads Indic digits too


def unknown_numbers(reply, allowed_texts) -> list[int]:
    """Numbers of 100 or more in a reply that appear in none of the allowed texts (the facts, the user's messages).

    This catches invented fees, dates and phone numbers. It can flag an honest "10,11" written without a space,
    so a person reads every flagged reply.
    """
    allowed = set()
    for text in allowed_texts:
        allowed |= numbers_in(text)
    return sorted(number for number in numbers_in(reply) if number >= 100 and number not in allowed)


def script_of(text) -> str:
    counts = {
        "odia": sum("\u0b00" <= ch <= "\u0b7f" for ch in text),
        "devanagari": sum("\u0900" <= ch <= "\u097f" for ch in text),
        "latin": sum(ch.isascii() and ch.isalpha() for ch in text),
    }
    if not any(counts.values()):
        return "none"
    # A reply that mixes native script with English words (course names) counts as the native script.
    for script in ("odia", "devanagari"):
        if counts[script] >= 5:
            return script
    return max(counts, key=counts.get)
