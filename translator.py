"""
translator.py
--------------
Modular translation layer. English -> Roman Urdu.

Design goal: swapping the translation backend should never require touching
the OCR, inpainting, or rendering code. Every backend implements the same
tiny interface (`Translator.translate_batch`), so `main.py` only ever talks
to that interface.

Backends included:
  - AnthropicTranslator   : uses the Anthropic Messages API (recommended)
  - OpenAITranslator      : uses the OpenAI Chat Completions API
  - EchoTranslator        : no-op / offline fallback, useful for dry runs
                            and for testing the pipeline without an API key

All backends batch multiple text blocks into a single request (with a
numbered-list protocol) to keep API calls and latency down on large
documents, and fall back to per-block calls if batch parsing fails.
"""

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class TranslationUnit:
    """One piece of text to translate, identified by an id so we can
    safely reassemble batched responses even if the model reorders lines."""
    id: int
    text: str


class Translator(ABC):
    """Common interface every translation backend must implement."""

    @abstractmethod
    def translate_batch(self, units: List[TranslationUnit]) -> dict:
        """Translate a batch of text units.

        Returns a dict {unit.id: translated_text}. Implementations should
        never raise for individual failures -- fall back to the original
        text for any unit that could not be translated, so the pipeline
        never crashes mid-document.
        """
        raise NotImplementedError

    # Shared helper used by all LLM-backed implementations -----------------
    @staticmethod
    def _build_prompt(units: List[TranslationUnit]) -> str:
        numbered = "\n".join(f"[{u.id}] {u.text}" for u in units if u.text.strip())
        return (
            "You are a professional English-to-Roman-Urdu translator working on "
            "a scanned document. Roman Urdu means Urdu written using the Latin "
            "(English) alphabet, NOT the Arabic/Nastaliq script -- e.g. "
            "'Aap kaise hain?' not 'آپ کیسے ہیں؟'.\n\n"
            "Rules:\n"
            "1. Translate every numbered line into natural, contextual Roman Urdu.\n"
            "2. Keep numbers, proper nouns, emails, URLs, and codes unchanged.\n"
            "3. Preserve the original line count -- one output line per input line.\n"
            "4. Keep translations concise; do not pad or add commentary.\n"
            "5. Output ONLY a JSON object mapping the line id (as a string) to the "
            "translated text, and nothing else. Example: {\"1\": \"...\", \"2\": \"...\"}\n\n"
            f"Lines to translate:\n{numbered}"
        )

    @staticmethod
    def _parse_json_response(raw: str, units: List[TranslationUnit]) -> dict:
        """Robustly parse a {id: text} JSON object out of a model response,
        tolerating stray markdown fences or leading/trailing chatter."""
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
            return {int(k): v for k, v in data.items()}
        except Exception:
            # Last resort: try to locate the first {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return {int(k): v for k, v in data.items()}
                except Exception:
                    pass
        # Give up gracefully -- caller will fill in originals as fallback
        return {}


class AnthropicTranslator(Translator):
    """Translation backend using Anthropic's Claude models.

    Requires: pip install anthropic
    API key via ANTHROPIC_API_KEY env var or constructor arg.
    """

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-6",
                 batch_size: int = 25, max_retries: int = 3):
        try:
            import anthropic  # local import so the package is optional
        except ImportError as e:
            raise ImportError(
                "The 'anthropic' package is required for AnthropicTranslator. "
                "Install it with: pip install anthropic"
            ) from e
        self._client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries

    def translate_batch(self, units: List[TranslationUnit]) -> dict:
        results: dict = {}
        for i in range(0, len(units), self._batch_size):
            chunk = units[i:i + self._batch_size]
            results.update(self._translate_chunk(chunk))
        return results

    def _translate_chunk(self, chunk: List[TranslationUnit]) -> dict:
        prompt = self._build_prompt(chunk)
        for attempt in range(self._max_retries):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=4000,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = "".join(
                    block.text for block in response.content if getattr(block, "type", "") == "text"
                )
                parsed = self._parse_json_response(raw_text, chunk)
                if parsed:
                    return {uid: parsed.get(uid, next(u.text for u in chunk if u.id == uid))
                            for uid in [u.id for u in chunk]}
            except Exception as e:
                print(f"  [translator] attempt {attempt + 1} failed: {e}")
                time.sleep(1.5 * (attempt + 1))
        # Fallback: return originals untranslated rather than crashing
        return {u.id: u.text for u in chunk}


class OpenAITranslator(Translator):
    """Translation backend using OpenAI's Chat Completions API.

    Requires: pip install openai
    API key via OPENAI_API_KEY env var or constructor arg.
    """

    def __init__(self, api_key: str | None = None, model: str = "gpt-4o-mini",
                 batch_size: int = 25, max_retries: int = 3):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "The 'openai' package is required for OpenAITranslator. "
                "Install it with: pip install openai"
            ) from e
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model
        self._batch_size = batch_size
        self._max_retries = max_retries

    def translate_batch(self, units: List[TranslationUnit]) -> dict:
        results: dict = {}
        for i in range(0, len(units), self._batch_size):
            chunk = units[i:i + self._batch_size]
            results.update(self._translate_chunk(chunk))
        return results

    def _translate_chunk(self, chunk: List[TranslationUnit]) -> dict:
        prompt = self._build_prompt(chunk)
        for attempt in range(self._max_retries):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                raw_text = response.choices[0].message.content or ""
                parsed = self._parse_json_response(raw_text, chunk)
                if parsed:
                    return {uid: parsed.get(uid, next(u.text for u in chunk if u.id == uid))
                            for uid in [u.id for u in chunk]}
            except Exception as e:
                print(f"  [translator] attempt {attempt + 1} failed: {e}")
                time.sleep(1.5 * (attempt + 1))
        return {u.id: u.text for u in chunk}


class EchoTranslator(Translator):
    """Offline fallback used when no API key is configured.

    It does NOT translate -- it simply tags the original text so the rest
    of the pipeline (layout, inpainting, rebuild) can be exercised and
    tested end-to-end without any network access or API cost.
    """

    def translate_batch(self, units: List[TranslationUnit]) -> dict:
        return {u.id: f"[UR] {u.text}" for u in units}


def get_translator(backend: str, api_key: str | None = None, model: str | None = None) -> Translator:
    """Factory used by main.py / CLI to build the requested backend."""
    backend = (backend or "echo").lower()
    if backend == "anthropic":
        return AnthropicTranslator(api_key=api_key, model=model or "claude-sonnet-4-6")
    if backend == "openai":
        return OpenAITranslator(api_key=api_key, model=model or "gpt-4o-mini")
    if backend == "echo":
        return EchoTranslator()
    raise ValueError(f"Unknown translator backend: {backend!r}. Choose from: anthropic, openai, echo")
