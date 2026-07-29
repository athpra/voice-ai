import asyncio
import difflib
import re
from datetime import date

from openai import AsyncOpenAI

from app.call_session import CallSession
from app.config import settings

PLAN_CATALOG = """- Basic 5GB -- $25/mo
- Standard 15GB -- $40/mo
- Business Pro 30GB -- $55/mo
- Family Share 50GB -- $65/mo
- Unlimited Plus 100GB -- $90/mo"""

SYSTEM_PROMPT_TEMPLATE = """You are a friendly voice support agent for DemoTel, a telecom \
provider. You are speaking with a caller over the phone, so keep replies short \
(1-2 sentences), conversational, and free of markdown, lists, or symbols -- \
everything you say will be read aloud by a text-to-speech engine.

Caller account details:
{context_block}

Plans you can offer, compare, or switch the caller to:
{plan_catalog}

Guidelines:
- Start your reply by directly engaging with the specific words the caller \
just used, not a generic opener -- this keeps you from sliding back into a \
canned answer you've already given.
- Answer exactly what the caller asked using the details above -- you have \
everything you need right now, so respond directly instead of saying you'll \
"check", "look into it", or "be right back".
- If the caller asks for something cheaper or different, recommend exactly \
ONE specific plan from the list above by name and price -- never list \
multiple plans or read out the whole catalog unless the caller explicitly \
asks to hear all the options.
- Never repeat a previous reply. If the caller pushes back or asks again, \
add new information or move the conversation forward instead of restating \
yourself.
- Once you've already recommended something and the caller says they want \
to think it over, are done with the topic, or will call back later, do not \
bring that recommendation up again -- just acknowledge them briefly and ask \
if there's anything else, even if they mention the topic again in passing.
- If something truly isn't covered above, say so plainly rather than \
guessing or stalling.
"""

# Cloudera AI Inference Service exposes an OpenAI-compatible endpoint, so the
# standard openai SDK works unmodified against a custom base_url. Real OpenAI
# models use a different request shape though: `max_completion_tokens` instead
# of `max_tokens`, and no `nvext` (that's specific to the NVIDIA NIM-style
# backend Cloudera AI Inference Service runs on) -- detect which one we're
# talking to so both keep working as CAII_BASE_URL gets swapped back and forth.
_client = AsyncOpenAI(base_url=settings.caii_base_url, api_key=settings.caii_api_key or "unused")
_IS_OPENAI = "api.openai.com" in settings.caii_base_url


def _format_context(context: dict) -> str:
    if not context:
        return "No account on file for this number -- treat the caller as a new/unrecognized customer."
    return "\n".join(f"- {key.replace('_', ' ')}: {value}" for key, value in context.items())


# Discourages literal token-for-token repetition across turns. This is a
# lexical-level fix only -- it stops the model from reusing the same exact
# wording, but does not stop it from giving the same semantic answer to a
# different question. The deterministic guards below handle that part.
_FREQUENCY_PENALTY = 0.4
_REPETITION_PENALTY = 1.15


async def _create_completion(messages: list[dict], max_tokens: int, temperature: float):
    """Cloudera AI Inference Service occasionally returns a transient error
    (e.g. a brief 403 right after a token refresh) that clears up a moment
    later -- one quick retry smooths over that without masking a real,
    persistent failure."""
    kwargs: dict = {
        "model": settings.caii_model_name,
        "messages": messages,
        "temperature": temperature,
        "frequency_penalty": _FREQUENCY_PENALTY,
    }
    if _IS_OPENAI:
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        # repetition_penalty isn't part of the standard OpenAI API -- this
        # endpoint's NVIDIA NIM-style backend expects it nested under `nvext`
        # instead of at the request root.
        kwargs["extra_body"] = {"nvext": {"repetition_penalty": _REPETITION_PENALTY}}

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            return await _client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(0.5)
    raise last_exc


_SENTENCE_END_RE = re.compile(r"^(.*[.!?])[^.!?]*$", re.DOTALL)


def _trim_to_complete_sentence(text: str) -> str:
    """If the model got cut off by max_tokens mid-sentence, trim back to the
    last complete sentence rather than speaking a reply that trails off
    mid-word -- a shorter complete reply reads far better over the phone
    than a longer one that just stops."""
    match = _SENTENCE_END_RE.match(text)
    return match.group(1).strip() if match else text


CLOSING_FALLBACK = "Got it -- let me know if there's anything else I can help with."

# Plan names as they appear in PLAN_CATALOG, for detecting when a reply
# re-pitches one.
_PLAN_NAMES = ("Basic 5GB", "Standard 15GB", "Business Pro 30GB", "Family Share 50GB", "Unlimited Plus")

_CLOSING_PATTERNS = re.compile(
    r"think(ing)? about it|that'?s all|no,? thanks?|no thank you|"
    r"i'?ll call back|that'?s it|nothing else|not (right )?now",
    re.IGNORECASE,
)


def _caller_is_closing(history: list[dict]) -> bool:
    """True if the caller's most recent turn signals they're done with the
    current topic (declining, deferring, or wrapping up)."""
    for turn in reversed(history):
        if turn["role"] == "user":
            return bool(_CLOSING_PATTERNS.search(turn["content"]))
    return False


def _mentions_a_plan(text: str) -> bool:
    return any(name.lower() in text.lower() for name in _PLAN_NAMES)


REPEAT_FALLBACK = "Sorry, I think I already said that -- could you tell me a bit more about what you're looking for?"
_REPEAT_THRESHOLD = 0.85


def _last_assistant_reply(history: list[dict]) -> str | None:
    for turn in reversed(history):
        if turn["role"] == "assistant":
            return turn["content"]
    return None


def _is_near_duplicate(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= _REPEAT_THRESHOLD


async def generate_reply(session: CallSession) -> str:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        context_block=_format_context(session.customer_context), plan_catalog=PLAN_CATALOG
    )
    messages = [
        {"role": "system", "content": system_prompt},
        *session.history,
    ]

    response = await _create_completion(messages, max_tokens=220, temperature=0.4)
    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    if choice.finish_reason == "length":
        text = _trim_to_complete_sentence(text) or text

    # The model doesn't reliably follow the "don't re-pitch once they're done"
    # guideline on its own (a known limitation at this model size). Detecting
    # the specific trigger -- caller just signaled they're closing the topic,
    # reply pitches a plan anyway -- deterministically catches that failure
    # without risking a false positive on a genuinely new question, the way a
    # generic text-similarity check would.
    if _caller_is_closing(session.history) and _mentions_a_plan(text):
        return CLOSING_FALLBACK

    # Separately, the model sometimes just regurgitates virtually the same
    # paragraph again regardless of what the caller actually just asked.
    # Comparing only against the immediately preceding reply (not every prior
    # one) with a high similarity bar catches that "stuck record" pattern
    # without misfiring on a reply that's merely on the same topic.
    previous = _last_assistant_reply(session.history)
    if previous and _is_near_duplicate(text, previous):
        text = REPEAT_FALLBACK
    return text


def _years_as_customer(customer_since_date: str) -> int:
    try:
        start = date.fromisoformat(customer_since_date)
    except (TypeError, ValueError):
        return 0
    return max((date.today() - start).days // 365, 0)


async def generate_greeting(session: CallSession, weather_blurb: str | None) -> str:
    """Builds the agent's proactive opening line for a known caller -- greets
    them by name, makes small talk, and thanks them for their tenure. This is
    a one-off instruction to the model, not a real caller utterance, so it's
    deliberately kept out of session.history; the caller is responsible for
    recording the returned greeting as the first assistant turn."""
    context = session.customer_context
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context_block=_format_context(context), plan_catalog=PLAN_CATALOG)
    years = _years_as_customer(context.get("customer_since_date", ""))
    weather_line = f" Naturally mention today's weather where they are: {weather_blurb}." if weather_blurb else ""
    instruction = (
        f"The caller, {context.get('full_name', 'the caller')}, has just connected. "
        f"Greet them warmly by first name and ask how they're doing today."
        f"{weather_line} Also thank them for being a {context.get('loyalty_tier', 'valued')}-tier "
        f"customer for {years} years. Keep it to two short, natural sentences."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]

    response = await _create_completion(messages, max_tokens=150, temperature=0.5)
    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    if choice.finish_reason == "length":
        text = _trim_to_complete_sentence(text) or text
    return text
