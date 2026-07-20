"""
app/integrations/telegram/security/phone_number.py — TelegramPhoneNumber value object.

[ADDITIVE] Part 2B — Phase 1 + Phase 2.

Immutable value object that encapsulates:
  * Validation — reject clearly invalid inputs.
  * Normalization — strip formatting, enforce E.164-style form.
  * Masking — produce a display-safe representation.

Normalization rules (documented for cross-mission contract):
  1. Trim outer whitespace.
  2. Remove interior spaces, hyphens ``-``, and parentheses ``()``.
  3. Require a leading ``+``.
  4. Require all remaining characters (after ``+``) to be ASCII digits.
  5. Require the digit portion to be 7–15 characters (E.164-style).

Masking rule (documented for cross-mission contract):
  * Country-code prefix: ``+1`` for NANP numbers (total length 11),
    otherwise ``+`` followed by the first 2 digits.
  * Middle: a single space followed by six asterisks ``******``.
  * Tail: the last 4 digits.
  * If the number is too short to mask safely (≤ 6 subscriber digits),
    all subscriber digits are masked with ``******`` and no tail is shown.
  * Ciphertext (``nexora:v1:…``) is never returned — ``masked()`` is only
    called on plaintext normalized numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.integrations.telegram.security.errors import (
    TelegramPhoneNumberValidationError,
)


# Pre-compiled patterns — module-level for performance.
_STRIP_CHARS_RE = re.compile(r"[\s\-\(\)]")
_DIGITS_ONLY_RE = re.compile(r"^\d+$")


@dataclass(frozen=True)
class TelegramPhoneNumber:
    """Immutable, validated, normalized Telegram phone number.

    Create instances only through :meth:`parse`; direct construction is
    intentionally kept available for testing but callers should not build
    instances with un-validated strings.
    """

    normalized: str
    """E.164-style string, always starting with ``+`` followed by 7–15 digits."""

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, value: str) -> TelegramPhoneNumber:
        """Validate and normalize a raw phone-number string.

        Parameters
        ----------
        value:
            Raw user input — may contain spaces, hyphens, and parentheses.

        Returns
        -------
        TelegramPhoneNumber
            Frozen value object with a clean E.164-style ``normalized`` form.

        Raises
        ------
        TelegramPhoneNumberValidationError
            If the input is empty, contains letters, is missing ``+``,
            or has an invalid digit length.
        """
        if not value or not value.strip():
            raise TelegramPhoneNumberValidationError("empty_input")

        cleaned = _STRIP_CHARS_RE.sub("", value.strip())

        if not cleaned:
            raise TelegramPhoneNumberValidationError("empty_after_strip")

        if not cleaned.startswith("+"):
            raise TelegramPhoneNumberValidationError("missing_plus_prefix")

        digits = cleaned[1:]  # everything after '+'

        if not digits:
            raise TelegramPhoneNumberValidationError("no_digits")

        # Reject any alphabetic or non-digit characters.
        if not _DIGITS_ONLY_RE.match(digits):
            raise TelegramPhoneNumberValidationError("contains_non_digits")

        if len(digits) < 7:
            raise TelegramPhoneNumberValidationError("too_short")

        if len(digits) > 15:
            raise TelegramPhoneNumberValidationError("too_long")

        normalized = f"+{digits}"
        return cls(normalized=normalized)

    # ------------------------------------------------------------------
    # Masking
    # ------------------------------------------------------------------

    def masked(self) -> str:
        """Return a display-safe masked representation.

        Masking rule (cross-mission contract — do not change without
        updating Mission 4's browser-verification recording):

        * NANP numbers (11 digits total): ``+1 ******XXXX``
        * Other numbers: ``+CC ******XXXX`` where CC is the first 2 digits.
        * If subscriber digits ≤ 6 (after removing country code), all
          subscriber digits are replaced: ``+CC ******`` with no tail.

        Examples::

            +919876543210  → +91 ******3210
            +14155552671   → +1 ******2671
            +442071838750  → +44 ******8750
        """
        digits = self.normalized[1:]  # strip leading '+'

        # Determine country-code length.
        # NANP: total 11 digits and starts with '1' → cc_len = 1
        # Everything else: cc_len = 2 (deterministic fallback).
        if len(digits) == 11 and digits[0] == "1":
            cc_len = 1
        else:
            cc_len = 2

        country_code = digits[:cc_len]
        subscriber = digits[cc_len:]

        tail_len = 4
        if len(subscriber) <= tail_len + 2:
            # Too few subscriber digits to show a meaningful tail safely.
            return f"+{country_code} ******"

        tail = subscriber[-tail_len:]
        return f"+{country_code} ******{tail}"

    # ------------------------------------------------------------------
    # Dunder overrides — never leak the full number
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Safe repr — uses the masked value, never the full number."""
        return f"TelegramPhoneNumber(masked={self.masked()!r})"

    def __str__(self) -> str:
        """Safe str — returns the masked value, never the full number."""
        return self.masked()
