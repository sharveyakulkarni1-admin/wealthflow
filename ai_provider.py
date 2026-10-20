from __future__ import annotations

import asyncio

import httpx
from google import genai
from google.genai.errors import APIError

from database import settings


class AIProviderError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def _gemini_input(messages: list[dict[str, str]]) -> tuple[str, str]:
    system_instructions = [
        message["content"]
        for message in messages
        if message.get("role") == "system"
    ]
    transcript = [
        f"{'Assistant' if message['role'] == 'assistant' else 'User'}:\n{message['content']}"
        for message in messages
        if message.get("role") in {"user", "assistant"}
    ]
    return "\n\n".join(system_instructions), "\n\n".join(transcript)


async def generate_response(messages: list[dict[str, str]]) -> str:
    if not settings.ai_api_key.strip():
        raise AIProviderError(
            "AI chat is not configured. Set WEALTHFLOW_AI_API_KEY in the server .env file and restart WealthFlow.",
            status_code=503,
        )

    system_instruction, prompt = _gemini_input(messages)
    try:
        async with genai.Client(api_key=settings.ai_api_key).aio as client:
            response = await client.interactions.create(
                model=settings.ai_model,
                input=prompt,
                system_instruction=system_instruction,
                store=False,
                generation_config={
                    "max_output_tokens": 700,
                    "thinking_level": "low",
                },
                timeout=settings.ai_timeout_seconds,
            )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise AIProviderError("The AI provider timed out. Please try again.", status_code=504) from None
    except APIError as exc:
        code = getattr(exc, "code", None)
        if code == 429:
            raise AIProviderError(
                "Gemini's rate limit was reached. Please try again later.",
                status_code=503,
            ) from None
        if code in {401, 403}:
            raise AIProviderError(
                "Gemini rejected the API key. Check WEALTHFLOW_AI_API_KEY in the server .env file.",
                status_code=503,
            ) from None
        if code == 400 and any(
            marker in str(exc).casefold()
            for marker in ("api key not valid", "invalid api key", "api_key_invalid")
        ):
            raise AIProviderError(
                "Gemini rejected the API key. Check WEALTHFLOW_AI_API_KEY in the server .env file.",
                status_code=503,
            ) from None
        if code == 404:
            raise AIProviderError(
                "The configured Gemini model was not found. Check WEALTHFLOW_AI_MODEL in the server .env file.",
                status_code=503,
            ) from None
        if code in {408, 504}:
            raise AIProviderError(
                "The AI provider timed out. Please try again.",
                status_code=504,
            ) from None
        if code in {500, 502, 503}:
            raise AIProviderError(
                "Gemini is temporarily unavailable. Please try again later.",
                status_code=502,
            ) from None
        raise AIProviderError(
            "Gemini could not process the request. Please try again later.",
            status_code=502,
        ) from None
    except httpx.RequestError:
        raise AIProviderError("The AI provider could not be reached. Please try again.", status_code=502) from None
    except Exception:
        raise AIProviderError(
            "Gemini request failed unexpectedly. Please try again later.",
            status_code=502,
        ) from None

    answer = (response.output_text or "").strip()
    if not answer:
        raise AIProviderError("Gemini returned an empty response. Please try again.")
    return answer[:12000]
