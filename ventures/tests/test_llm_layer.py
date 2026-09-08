"""Exercise the Claude code path without network: stub the SDK client so we know
the wrapper parses structured output, counts usage, and handles refusals."""
import json
import types


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.stop_reason = stop
        self.content = [types.SimpleNamespace(type="text", text=text)]
        self.usage = types.SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=50)


class _FakeClient:
    def __init__(self, resp):
        self.calls = []
        create = lambda **kw: (self.calls.append(kw), resp)[1]
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))


def _llm(monkeypatch, resp):
    import anthropic
    from ventures.core import llm as mod
    fake = _FakeClient(resp)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: fake)
    return mod.LLM(), fake


def test_json_roundtrip_and_usage(monkeypatch):
    llm, fake = _llm(monkeypatch, _Resp(json.dumps({"a": 1})))
    out = llm.json({"type": "object"}, "hi", system="sys", effort="low")
    assert out == {"a": 1}
    kw = fake.calls[0]
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "low"
    assert kw["thinking"] == {"type": "adaptive"} and kw["fallbacks"] and kw["betas"]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert llm.usage.calls == 1 and llm.usage.cache_read_tokens == 50 and llm.usage.cost_usd > 0


def test_refusal_returns_none(monkeypatch):
    llm, _ = _llm(monkeypatch, _Resp("", stop="refusal"))
    assert llm.json({"type": "object"}, "x") is None
    assert llm.text("x") is None


def test_products_survive_bad_model_output(monkeypatch):
    """Every product must fall back to rules when the model returns junk."""
    llm, _ = _llm(monkeypatch, _Resp("not json"))
    from ventures.core import llm as mod
    monkeypatch.setattr(mod, "_llm", llm)
    monkeypatch.delenv("VENTURES_OFFLINE", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    from ventures.leasecheck import review
    r = review("Tenant waives the right to a jury trial.", "TX")
    assert any(f["rule"] == "waiver" for f in r["findings"])
    from ventures.dunning.engine import Invoice
    from ventures.dunning.messages import compose
    from datetime import date
    assert "INV" in compose(Invoice("INV-1", "A B", "a@b", 10, date(2026, 9, 1)), "gentle", date(2026, 9, 5), "S", voice="warm")["subject"]
