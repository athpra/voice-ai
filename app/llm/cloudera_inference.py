from openai import AsyncOpenAI

from app.call_session import CallSession
from app.config import settings

SYSTEM_PROMPT_TEMPLATE = """You are a friendly voice support agent for DemoTel, a telecom \
provider. You are speaking with a caller over the phone, so keep replies short \
(1-2 sentences), conversational, and free of markdown, lists, or symbols -- \
everything you say will be read aloud by a text-to-speech engine.

Caller account details:
{context_block}

Use these details to answer questions about their plan, billing, or support \
tickets. If something isn't covered above, say you don't have that \
information rather than guessing.
"""

# Cloudera AI Inference Service exposes an OpenAI-compatible endpoint, so the
# standard openai SDK works unmodified against a custom base_url.
_client = AsyncOpenAI(base_url=settings.caii_base_url, api_key=settings.caii_api_key or "unused")


def _format_context(context: dict) -> str:
    if not context:
        return "No account on file for this number -- treat the caller as a new/unrecognized customer."
    return "\n".join(f"- {key.replace('_', ' ')}: {value}" for key, value in context.items())


async def generate_reply(session: CallSession, user_utterance: str) -> str:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context_block=_format_context(session.customer_context))
    messages = [
        {"role": "system", "content": system_prompt},
        *session.history,
        {"role": "user", "content": user_utterance},
    ]

    response = await _client.chat.completions.create(
        model=settings.caii_model_name,
        messages=messages,
        max_tokens=150,
        temperature=0.4,
    )
    return (response.choices[0].message.content or "").strip()
