from app.config import settings
from app.llm.cloudera_inference import _apply_thinking_directive, _strip_reasoning


def test_strips_closed_think_block():
    raw = "<think>\nThe caller said hi. I should greet them.\n</think>\n\nHi there, how can I help?"
    assert _strip_reasoning(raw) == "Hi there, how can I help?"


def test_strips_reasoning_terminated_by_bare_close_tag():
    # NIM's reasoning parser eats the opening <think> but the model still
    # emits the closing tag.
    raw = "We need to greet Athul and mention the weather.\n</think>\n\nHi Athul, how are you today?"
    assert _strip_reasoning(raw) == "Hi Athul, how are you today?"


def test_strips_unclosed_think_block_to_empty():
    # Reasoning ran into the max_tokens cap before ever closing the tag --
    # there's no answer in here, only scratch thinking.
    raw = '<think>\nWe need to greet by first name (Athul). Sentence 1: "Hi Athul,'
    assert _strip_reasoning(raw) == ""


def test_leaves_plain_reply_untouched():
    assert _strip_reasoning("Hi Athul, how are you doing today?") == "Hi Athul, how are you doing today?"


def test_thinking_directive_folded_into_prompt_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "caii_thinking_directive", "detailed thinking off")
    assert _apply_thinking_directive("You are an agent.") == "detailed thinking off\n\nYou are an agent."


def test_thinking_directive_noop_when_blank(monkeypatch):
    monkeypatch.setattr(settings, "caii_thinking_directive", "")
    assert _apply_thinking_directive("You are an agent.") == "You are an agent."
