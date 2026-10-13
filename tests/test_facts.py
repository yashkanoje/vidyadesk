import copy

import pytest

from helpers import FACTS
from leadagent.facts import FactsError, load_facts_file, parse_facts, render_facts


def test_valid_facts_load():
    facts = parse_facts(FACTS)
    assert facts.courses[0].fee == "₹68,000 per year"


def test_missing_fee_is_rejected_and_names_the_field():
    bad = copy.deepcopy(FACTS)
    del bad["courses"][0]["fee"]
    with pytest.raises(FactsError) as err:
        parse_facts(bad)
    assert "courses.0.fee" in str(err.value)


def test_unknown_field_is_rejected():
    bad = copy.deepcopy(FACTS)
    bad["discount"] = "50%"
    with pytest.raises(FactsError) as err:
        parse_facts(bad)
    assert "discount" in str(err.value)


def test_no_courses_is_rejected():
    bad = copy.deepcopy(FACTS)
    bad["courses"] = []
    with pytest.raises(FactsError):
        parse_facts(bad)


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(FactsError):
        load_facts_file(path)


def test_malformed_yaml_is_rejected(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("courses: [unclosed", encoding="utf-8")
    with pytest.raises(FactsError):
        load_facts_file(path)


def test_render_includes_every_fee_and_batch():
    text = render_facts(parse_facts(FACTS))
    assert "₹68,000 per year" in text
    assert "₹62,000 per year" in text
    assert "Mon to Sat 4 pm to 6:30 pm" in text
    assert "the first two classes are free" in text
