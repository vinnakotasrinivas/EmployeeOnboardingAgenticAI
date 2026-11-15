from __future__ import annotations

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_CANDIDATE = re.compile(r"(?<!\w)\+?\(?\d[\d\s().-]{6,}\d(?!\w)")
LONG_DIGITS = re.compile(r"\d{9,}")
MIN_PHONE_DIGITS = 10  # dates like 2026-10-29 have 8 digits and stay readable


def _phone(match: re.Match) -> str:
    digits = sum(ch.isdigit() for ch in match.group())
    return "[PHONE]" if digits >= MIN_PHONE_DIGITS else match.group()


def mask_pii(text: str) -> str:
    """Mask emails, US SSNs, phone numbers and long digit runs, for logs only."""
    text = EMAIL.sub("[EMAIL]", text)
    text = SSN.sub("[SSN]", text)
    text = PHONE_CANDIDATE.sub(_phone, text)
    return LONG_DIGITS.sub("[NUMBER]", text)
