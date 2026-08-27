
import pytest

from btwin import LLM, CostMeter
from btwin.llm import _ExtractJSON, _StripFences


class FakeMessage:
    """Stands in for an AIMessage, so nothing here needs a network or a key."""

    def __init__(self, content="ok", promptTokens=100, completionTokens=20, cost=1.1e-06,
                 model="test/model"):
        self.content = content
        usage = {"prompt_tokens": promptTokens, "completion_tokens": completionTokens}
        if cost is not None:
            usage["cost"] = cost
        self.response_metadata = {"model_name": model, "token_usage": usage}


class TestStripFences:
    def test_plain_text_untouched(self):
        assert _StripFences("SELECT ?s WHERE { ?s ?p ?o }") == "SELECT ?s WHERE { ?s ?p ?o }"

    def test_removes_fences(self):
        assert _StripFences("```\nSELECT ?s\n```") == "SELECT ?s"

    def test_removes_sparql_tag(self):
        assert _StripFences("```sparql\nSELECT ?s\n```") == "SELECT ?s"

    def test_drops_prose_around_the_block(self):
        assert _StripFences("Here you go:\n```sparql\nASK { ?s ?p ?o }\n```\nHope it helps!") \
            == "ASK { ?s ?p ?o }"


class TestCostMeterRecord:
    def test_records_tokens_and_cost(self):
        meter = CostMeter()
        call = meter.Record("agent 3 write", FakeMessage())
        assert call["promptTokens"] == 100
        assert call["completionTokens"] == 20
        assert call["cost"] == pytest.approx(1.1e-06)

    def test_provider_cost_is_not_estimated(self):
        meter = CostMeter()
        assert meter.Record("t", FakeMessage())["estimated"] is False

    def test_missing_cost_is_estimated(self):
        # An unroutable base URL keeps the price lookup offline: the cost falls back to 0.0
        meter = CostMeter(baseURL="http://127.0.0.1:9")
        call = meter.Record("t", FakeMessage(cost=None))
        assert call["estimated"] is True
        assert call["cost"] == 0.0

    def test_labels_the_agent(self):
        meter = CostMeter()
        assert meter.Record("answer", FakeMessage())["agent"] == "answer"

    def test_falls_back_to_the_meter_model(self):
        meter = CostMeter(model="fallback/model")
        message = FakeMessage()
        message.response_metadata["model_name"] = None
        assert meter.Record("t", message)["model"] == "fallback/model"

    def test_message_without_metadata(self):
        meter = CostMeter(baseURL="http://127.0.0.1:9")
        call = meter.Record("t", object())
        assert call["promptTokens"] == 0 and call["cost"] == 0.0


class TestCostMeterTotal:
    def test_sums_every_call(self):
        meter = CostMeter()
        meter.Record("a", FakeMessage())
        meter.Record("b", FakeMessage())
        total = meter.Total()
        assert total["calls"] == 2
        assert total["promptTokens"] == 200
        assert total["cost"] == pytest.approx(2.2e-06)

    def test_start_index_subtotals_one_question(self):
        meter = CostMeter()
        meter.Record("a", FakeMessage())
        first = len(meter.calls)
        meter.Record("b", FakeMessage())
        assert meter.Total(first)["calls"] == 1

    def test_empty_meter(self):
        total = CostMeter().Total()
        assert total["calls"] == 0 and total["cost"] == 0.0
        assert total["estimated"] is False


class TestCostMeterFormat:
    def test_keeps_six_decimals(self):
        # A call costs a few millionths of a dollar; 2 decimals would read as $0.00
        assert CostMeter.Format(1.1e-06) == "$0.000001"

    def test_describe(self):
        meter = CostMeter()
        assert CostMeter.Describe(meter.Record("t", FakeMessage())) == "100+20 tokens, $0.000001"

    def test_describe_marks_estimates(self):
        meter = CostMeter(baseURL="http://127.0.0.1:9")
        assert CostMeter.Describe(meter.Record("t", FakeMessage(cost=None))).endswith("(estimated)")


class TestConstructor:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ValueError):
            LLM.Constructor()

    def test_invalid_model_type_raises(self):
        with pytest.raises(TypeError):
            LLM.Constructor(model=123, apiKey="sk-or-test")

    def test_builds_with_explicit_key(self):
        pytest.importorskip("langchain_openai")
        llm = LLM.Constructor(model="test/model", apiKey="sk-or-test")
        assert llm.model_name == "test/model"

    def test_reads_key_from_environment(self, monkeypatch):
        pytest.importorskip("langchain_openai")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-from-env")
        monkeypatch.setenv("OPENROUTER_MODEL", "env/model")
        assert LLM.Constructor().model_name == "env/model"


class TestExtractJSON:
    def test_plain_object(self):
        assert _ExtractJSON('{"a": 1}') == '{"a": 1}'

    def test_removes_fences_and_tag(self):
        assert _ExtractJSON('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_drops_prose_around_the_object(self):
        assert _ExtractJSON('Sure!\n{"a": 1}\nDone.') == '{"a": 1}'

    def test_no_braces_gives_empty(self):
        # Lets the caller say "no JSON" instead of reporting prose as malformed JSON
        assert _ExtractJSON("I cannot do that.") == ""


class TestChainAndComplete:
    def test_chain_needs_a_system_prompt(self):
        pytest.importorskip("langchain_core")
        with pytest.raises(ValueError):
            LLM.Chain(object(), "")

    def test_chain_needs_a_model(self):
        pytest.importorskip("langchain_core")
        with pytest.raises(ValueError):
            LLM.Chain(None, "a system prompt")

    def test_complete_needs_a_prompt(self):
        with pytest.raises(ValueError):
            LLM.Complete(object(), "a system prompt", "")
