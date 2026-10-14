import pytest
from pydantic import ValidationError

from leadagent.agent import graph as graph_module
from leadagent.settings import Settings, get_settings


@pytest.fixture
def gemini(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    graph_module.get_graph.cache_clear()
    graph_module.get_plain_model.cache_clear()
    yield
    graph_module.get_graph.cache_clear()
    graph_module.get_plain_model.cache_clear()


def capture_build_graph(monkeypatch):
    captured = {}

    def fake_build_graph(model, checkpointer, cache_prompt=True):
        captured.update(model=model, cache_prompt=cache_prompt)

    monkeypatch.setattr(graph_module, "build_graph", fake_build_graph)
    return captured


def tool_names(bound_model):
    # Gemini's binding holds the tools in the {"type": "function", "function": {...}} format
    return {tool["function"]["name"] for tool in bound_model.kwargs["tools"]}


def test_claude_is_the_default_provider():
    assert get_settings().llm_provider == "anthropic"


def test_an_unknown_provider_is_rejected():
    with pytest.raises(ValidationError):
        Settings(llm_provider="openai")


def test_the_gemini_provider_builds_a_gemini_agent_without_prompt_caching(gemini, monkeypatch):
    captured = capture_build_graph(monkeypatch)
    graph_module.get_graph()
    model = captured["model"]
    assert type(model.bound).__name__ == "ChatGoogleGenerativeAI"
    assert model.bound.model.endswith("gemini-3.5-flash-lite")
    assert tool_names(model) == {"save_lead", "set_interest", "handoff"}
    assert captured["cache_prompt"] is False  # the cached-block format is Anthropic's


def test_the_gemini_provider_also_writes_the_nudges(gemini):
    assert type(graph_module.get_plain_model()).__name__ == "ChatGoogleGenerativeAI"


def test_the_eval_runner_can_use_gemini(gemini):
    from evals.run import make_model

    model, cache_prompt = make_model("gemini")
    assert type(model.bound).__name__ == "ChatGoogleGenerativeAI"
    assert cache_prompt is False
