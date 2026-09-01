from app.config import settings
from app.llm.cloudera_inference import _strip_reasoning, _with_thinking_directive


def test_strips_closed_think_block():
    raw = "<think>\nThe caller said hi. I should greet them.\n</think>\n\nHi there, how can I help?"
    assert _strip_reasoning(raw) == "Hi there, how can I help?"


def test_strips_unclosed_think_block_to_empty():
    # Reasoning ran into the max_tokens cap before ever closing the tag --
    # there's no answer in here, only scratch thinking.
    raw = "<think>\nWe need to greet by first name (Athul). Sentence 1: \"Hi Athul,"
    assert _strip_reasoning(raw) == ""


def test_leaves_plain_reply_untouched():
    assert _strip_reasoning("Hi Athul, how are you doing today?") == "Hi Athul, how are you doing today?"


def test_thinking_directive_prepended_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "caii_thinking_directive", "detailed thinking off")
    messages = [{"role": "system", "content": "prompt"}, {"role": "user", "content": "hi"}]
    result = _with_thinking_directive(messages)
    assert result[0] == {"role": "system", "content": "detailed thinking off"}
    assert result[1:] == messages


def test_thinking_directive_noop_when_blank(monkeypatch):
    monkeypatch.setattr(settings, "caii_thinking_directive", "")
    messages = [{"role": "user", "content": "hi"}]
    assert _with_thinking_directive(messages) == messages
