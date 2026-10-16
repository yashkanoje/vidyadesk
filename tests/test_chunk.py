from leadagent.rag.chunk import chunk_text


def words(n, start=0):
    return " ".join(f"w{i}" for i in range(start, start + n))


def test_empty_text_gives_no_passages():
    assert chunk_text("") == []
    assert chunk_text("  \n\n  ") == []


def test_short_paragraphs_are_packed_together_and_kept_whole():
    text = "Fees\n\nThe fee is 100.\n\nTransport\n\nBuses run daily."
    assert chunk_text(text, max_words=50) == ["Fees\n\nThe fee is 100.\n\nTransport\n\nBuses run daily."]


def test_a_new_passage_starts_at_a_paragraph_boundary():
    first, second = words(30), words(30, 100)
    passages = chunk_text(f"{first}\n\n{second}", max_words=40, overlap_words=5)
    assert passages == [first, second]


def test_a_short_heading_is_carried_into_the_next_passage():
    heading, body_a, body_b = "Refund policy", words(30), words(30, 100)
    passages = chunk_text(f"{body_a}\n\n{heading}\n\n{body_b}", max_words=40, overlap_words=5)
    assert passages[-1] == f"{heading}\n\n{body_b}"


def test_a_long_paragraph_is_cut_into_overlapping_windows():
    passages = chunk_text(words(100), max_words=40, overlap_words=10)
    assert len(passages) == 3
    assert passages[0].split()[-10:] == passages[1].split()[:10]


def test_no_passage_is_far_over_the_limit_and_no_word_is_lost():
    text = "\n\n".join(words(n, start) for n, start in ((10, 0), (70, 100), (5, 300), (45, 400)))
    passages = chunk_text(text, max_words=40, overlap_words=8)
    assert all(len(p.split()) <= 48 for p in passages)
    assert set(text.split()) <= set(" ".join(passages).split())


def test_line_breaks_inside_a_paragraph_become_spaces():
    assert chunk_text("Buses run\nfrom Sector 19\n daily.") == ["Buses run from Sector 19 daily."]
