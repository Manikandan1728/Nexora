"""
app/integrations/telegram/mapping/sender_resolver.py

[ADDITIVE] — New file. Resolves sender identity from Telegram event data.

The key design rule: sender_id (telegram_user_id) is the stable retrieval
key. sender_name is for display only and must never be used as a filter.
"""

from __future__ import annotations


class SenderResolver:
    """
    Extracts and validates sender identity from a raw Telegram event dict.

    Separates the stable sender_id from the mutable display sender_name.
    If sender_id is absent (system messages), both are None.
    """

    @staticmethod
    def resolve(event: dict) -> tuple[str | None, str | None]:
        """
        Extract (sender_id, sender_name) from a Telegram event dict.

        Args:
            event: Raw Telegram event dictionary (from fixture or TDLib).

        Returns:
            (sender_id, sender_name) — both may be None for system messages.
            sender_id is always the stable identifier; sender_name is display-only.
        """
        sender_id: str | None = event.get("sender_id")
        sender_name: str | None = event.get("sender_name")

        # Normalize empty strings to None
        if sender_id and not sender_id.strip():
            sender_id = None
        if sender_name and not sender_name.strip():
            sender_name = None

        return sender_id, sender_name
