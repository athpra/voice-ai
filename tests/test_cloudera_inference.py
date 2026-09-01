from types import SimpleNamespace

from app.config import settings
from app.llm.cloudera_inference import _apply_thinking_directive, _spoken_text, _strip_reasoning


def _choice(content, finish_reason="stop", reasoning_content=None):
    message = SimpleNamespace(
        content=content,
        reasoning_content=None,
        model_extra={"reasoning_content": reasoning_content} if reasoning_content else {},
    )
    return SimpleNamespace(message=message, finish_reason=finish_reason)


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


def test_spoken_text_recovers_answer_misfiled_into_reasoning_content():
    choice = _choice("", finish_reason="stop", reasoning_content="Hi Athul, your plan looks fine.")
    assert _spoken_text(choice) == "Hi Athul, your plan looks fine."


def test_spoken_text_does_not_recover_reasoning_on_length_truncation():
    choice = _choice("", finish_reason="length", reasoning_content="we should think about the plan and")
    assert _spoken_text(choice) == ""


def test_spoken_text_trims_genuine_answer_truncation_to_last_sentence():
    choice = _choice("You have used 42 GB. Well under your limit. You can also", finish_reason="length")
    assert _spoken_text(choice) == "You have used 42 GB. Well under your limit."


def test_spoken_text_discards_unclosed_think_on_truncation():
    choice = _choice("<think>we need to figure out the plan and", finish_reason="length")
    assert _spoken_text(choice) == ""


def test_spoken_text_passes_clean_answer_through():
    assert _spoken_text(_choice("Hi Athul, how are you today?")) == "Hi Athul, how are you today?"
