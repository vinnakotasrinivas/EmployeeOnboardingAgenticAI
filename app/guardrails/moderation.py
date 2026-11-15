"""Safety moderation: Groq guard model (Llama Guard or gpt-oss-safeguard), with a rule-based fallback."""

from __future__ import annotations

import functools
import logging
import re
from typing import Literal

from app.config import settings
from app.guardrails.pii import mask_pii
from app.llm.groq_client import check_models, get_chat, strip_think

logger = logging.getLogger("onboardiq.guardrails")

Role = Literal["user", "assistant"]

SAFEGUARD_POLICY = """Classify whether the CONTENT violates this safety policy.
Unsafe categories: S1 violent crime or threats; S2 non-violent crime (hacking, fraud, theft, drugs);
S3 sexual content; S4 child exploitation; S5 hate or harassment; S6 self-harm or suicide;
S7 weapons or explosives; S8 malicious code or credential theft.
Everything else is safe, including normal workplace and HR questions, people lookups, and security
how-tos such as setting up MFA, VPN or passwords.
Answer with exactly one line: "safe" or "unsafe: S<n>[,S<n>]"."""

_RULES: list[tuple[str, re.Pattern]] = [
    ("violence", re.compile(r"\b(kill|murder|shoot|stab|bomb|explosive|attack)\b.{0,40}\b(someone|people|him|her|them|my|colleague|manager|coworker|office)\b", re.I)),
    ("weapons", re.compile(r"\b(make|build|buy)\b.{0,20}\b(bomb|explosive|gun|weapon)s?\b", re.I)),
    ("self_harm", re.compile(r"\b(suicide|kill myself|hurt myself|self[- ]harm|end my life)\b", re.I)),
    ("illegal", re.compile(r"\b(steal|hack into|phish|launder|bypass security|crack (the |a )?password|buy drugs)\b", re.I)),
]

_fallback_logged = False


def _parse(output: str) -> tuple[bool, list[str]]:
    lines = [line.strip() for line in strip_think(output).splitlines() if line.strip()]
    if not lines:
        raise ValueError("empty guard output")
    first = lines[0].lower()
    if first.startswith("safe"):
        return True, []
    if first.startswith("unsafe"):
        codes = first.split(":", 1)[1] if ":" in first else (lines[1] if len(lines) > 1 else "")
        return False, [c.strip().upper() for c in codes.split(",") if c.strip()]
    raise ValueError(f"unexpected guard output: {lines[0][:50]!r}")


def rule_based(text: str) -> tuple[bool, list[str]]:
    flagged = [name for name, pattern in _RULES if pattern.search(text)]
    return not flagged, flagged


def _use_fallback(text: str, why: str) -> tuple[bool, list[str]]:
    global _fallback_logged
    if not _fallback_logged:
        logger.warning("Moderation: using rule-based fallback (%s).", why)
        _fallback_logged = True
    return rule_based(text)


@functools.lru_cache(maxsize=256)
def moderate(text: str, role: Role = "user") -> tuple[bool, list[str]]:
    """Return (safe, categories). Never raises; falls back to keyword rules if the guard model fails."""
    model = settings.groq_guard_model
    if not settings.groq_api_key.strip() or not check_models().get("guard_model_ok"):
        return _use_fallback(text, f"guard model '{model}' unavailable")
    try:
        if "llama-guard" in model.lower():
            chat = get_chat(model, temperature=0.0, hide_reasoning=False)
            messages = [("user", text)] if role == "user" else [("user", "(question)"), ("assistant", text)]
        else:
            chat = get_chat(model, temperature=0.0, hide_reasoning=False, reasoning_effort="low",
                            model_kwargs={"include_reasoning": False})
            label = "a user's question" if role == "user" else "an assistant's answer"
            messages = [("system", SAFEGUARD_POLICY), ("user", f"CONTENT ({label}):\n{text}")]
        # Called directly, not via invoke_text: on a rate limit we fall back at once rather than wait.
        safe, categories = _parse(str(chat.invoke(messages).content))
    except Exception as exc:  # noqa: BLE001 - moderation must never break answering
        logger.info("Moderation call failed (%s); using rules for %r", type(exc).__name__, mask_pii(text[:80]))
        return rule_based(text)
    if not safe:
        logger.warning("Moderation flagged %s text %s: %r", role, categories, mask_pii(text[:120]))
    return safe, categories
