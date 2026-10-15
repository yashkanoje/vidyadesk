import pytest

from helpers import FakeEmbedder
from leadagent.rag import embed


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_tests_use_the_fake_embedder():
    assert isinstance(embed.get_embedder(), FakeEmbedder)


@pytest.mark.model
def test_the_real_model_gives_384_numbers_and_ranks_by_meaning():
    model = embed.FastEmbedder()
    query = model.query("How much does the bus cost each month?")
    bus, jee = model.passages(
        [
            "Buses run from Sector 19 and Udit Nagar; transport costs 1,200 rupees a month.",
            "The JEE batch for Class 11 starts in April.",
        ]
    )
    assert len(query) == len(bus) == embed.DIMS
    assert dot(query, bus) > dot(query, jee)
