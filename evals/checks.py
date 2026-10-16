import re

from leadagent.language import script_of  # noqa: F401 (re-exported for evals/run.py and tests)

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


def passage_hit(passages, phrase) -> bool:
    return any(phrase.lower() in passage.lower() for passage in passages)


def suggest_floor(answerable, unanswerable) -> float:
    """The similarity floor that sorts the most questions correctly into "answer" and "hand off".

    Each observed score is tried as the floor; ties go to the lower floor.
    """
    best, best_correct = 0.0, -1
    for floor in sorted(set(answerable) | set(unanswerable)):
        correct = sum(score >= floor for score in answerable) + sum(score < floor for score in unanswerable)
        if correct > best_correct:
            best, best_correct = floor, correct
    return round(best, 3)
