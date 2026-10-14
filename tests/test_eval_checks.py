from evals.checks import numbers_in, script_of, unknown_numbers

FACTS_TEXT = "Fee: ₹68,000 per year. Address: Rourkela 769004. Phone: 0661-2400000"


def test_a_fee_from_the_facts_passes():
    assert unknown_numbers("The fee is ₹68,000 per year.", [FACTS_TEXT]) == []
    assert unknown_numbers("Fee is Rs 68000.", [FACTS_TEXT]) == []


def test_an_invented_fee_is_flagged():
    assert unknown_numbers("The fee is ₹55,000 and you save ₹13,000.", [FACTS_TEXT]) == [13000, 55000]


def test_devanagari_and_odia_digits_are_understood():
    assert unknown_numbers("फीस ₹६८,००० है", [FACTS_TEXT]) == []
    assert unknown_numbers("ଫି ୫୫,୦୦୦ ଟଙ୍କା", [FACTS_TEXT]) == [55000]


def test_small_numbers_are_ignored():
    assert unknown_numbers("Class 11 batch runs 5 pm to 7:30 pm, 6 days a week.", [FACTS_TEXT]) == []


def test_a_number_the_user_gave_is_allowed():
    assert unknown_numbers("I have noted 9861012345.", [FACTS_TEXT, "my number is 9861012345"]) == []


def test_numbers_in_reads_grouped_digits():
    assert numbers_in("1,00,000 and 2400000 and 7") == {100000, 2400000, 7}


def test_script_of():
    assert script_of("ନମସ୍କାର, ଫି କେତେ?") == "odia"
    assert script_of("नमस्ते, फीस कितनी है?") == "devanagari"
    assert script_of("namaskar, fees kete?") == "latin"
    assert script_of("JEE की फीस ₹68,000 है") == "devanagari"
    assert script_of("123 ?!") == "none"
