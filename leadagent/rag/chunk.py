import re


def chunk_text(text, max_words=100, overlap_words=20):
    """Split text into passages of about max_words words, breaking between paragraphs where possible.

    A paragraph longer than max_words is cut into windows that overlap by overlap_words. When a new passage
    starts, it repeats the previous passage's last paragraph if that is short (overlap_words or fewer), so a
    heading stays with the text after it. Passages can therefore reach max_words + overlap_words.
    """
    pieces = []
    for paragraph in re.split(r"\n\s*\n", text):
        words = paragraph.split()
        while len(words) > max_words:
            pieces.append(" ".join(words[:max_words]))
            words = words[max_words - overlap_words :]
        if words:
            pieces.append(" ".join(words))

    passages, current, size = [], [], 0
    for piece in pieces:
        count = len(piece.split())
        if current and size + count > max_words:
            passages.append("\n\n".join(current))
            tail = current[-1]
            current, size = ([tail], len(tail.split())) if len(tail.split()) <= overlap_words else ([], 0)
        current.append(piece)
        size += count
    if current:
        passages.append("\n\n".join(current))
    return passages
