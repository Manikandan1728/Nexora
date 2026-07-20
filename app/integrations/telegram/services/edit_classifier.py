"""
app/integrations/telegram/services/edit_classifier.py

[ADDITIVE] Edit ordering and classification logic.

Decision Record DR-M1 (Phase 1):
  Primary signal: internal message_version + stored edit_timestamp.
  Tie-break: update_id string comparison when timestamps are equal.
  Reason: Telegram edit_date is reliable; update_id breaks rapid re-edit ties.
  Rollback: change classify_edit() tie-break; no schema change required.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class EditAction(str, Enum):
    APPLY           = "apply"           # Accept and process this edit
    DUPLICATE       = "duplicate"       # Same idempotency key already completed
    STALE           = "stale"           # Older than current stored version
    DELETED         = "deleted"         # Tombstone exists; do not recreate
    UNKNOWN_MESSAGE = "unknown_message" # No DB record; apply upsert policy


@dataclass(frozen=True)
class EditDecision:
    action: EditAction
    reason: str

    @property
    def should_apply(self) -> bool:
        return self.action == EditAction.APPLY

    @property
    def should_skip(self) -> bool:
        return self.action in (EditAction.DUPLICATE, EditAction.STALE, EditAction.DELETED)


def classify_edit(
    *,
    tombstone_exists: bool,
    idempotency_key_completed: bool,
    message_exists: bool,
    current_version: Optional[int],
    current_edit_timestamp: Optional[datetime],
    incoming_edit_timestamp: Optional[datetime],
    incoming_update_id: Optional[str],
    current_update_id: Optional[str],
) -> EditDecision:
    """
    Classify an incoming edit event without any I/O.

    Args:
        tombstone_exists:         True if a deletion tombstone exists.
        idempotency_key_completed: True if this idempotency key already completed.
        message_exists:           True if the message exists in DB.
        current_version:          Stored message_version (None if message doesn't exist).
        current_edit_timestamp:   Stored last edit timestamp (None if never edited).
        incoming_edit_timestamp:  Timestamp of the incoming edit event.
        incoming_update_id:       Update ID from the incoming event (opaque string).
        current_update_id:        Update ID last applied (for tie-break).

    Returns:
        EditDecision with action and human-readable reason.
    """
    # 1. Tombstone check — deleted messages cannot be revived
    if tombstone_exists:
        return EditDecision(
            action=EditAction.DELETED,
            reason="Deletion tombstone exists; message cannot be revived by an edit.",
        )

    # 2. Idempotency check — same key already fully processed
    if idempotency_key_completed:
        return EditDecision(
            action=EditAction.DUPLICATE,
            reason="Idempotency key already completed; returning cached result.",
        )

    # 3. Unknown message — no DB record exists
    if not message_exists:
        return EditDecision(
            action=EditAction.UNKNOWN_MESSAGE,
            reason="No message record found; will apply upsert-if-reconstructible policy.",
        )

    # 4. Stale check — incoming edit is older than what we already have
    if current_edit_timestamp is not None and incoming_edit_timestamp is not None:
        # Normalize to UTC for comparison
        curr_ts = _to_utc(current_edit_timestamp)
        inc_ts  = _to_utc(incoming_edit_timestamp)

        if inc_ts < curr_ts:
            return EditDecision(
                action=EditAction.STALE,
                reason=(
                    f"Incoming edit_timestamp {inc_ts.isoformat()} is older than "
                    f"current {curr_ts.isoformat()}; ignoring stale event."
                ),
            )

        if inc_ts == curr_ts:
            # Tie-break: higher update_id string wins (DR-M1)
            if (
                incoming_update_id is not None
                and current_update_id is not None
                and incoming_update_id <= current_update_id
                and incoming_update_id != current_update_id
            ):
                return EditDecision(
                    action=EditAction.STALE,
                    reason=(
                        f"Same timestamp but update_id {incoming_update_id!r} "
                        f"<= current {current_update_id!r}; treating as stale."
                    ),
                )

    # 5. Accept the edit
    return EditDecision(
        action=EditAction.APPLY,
        reason=f"Edit accepted; will increment version from {current_version}.",
    )


def _to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC, treating naive as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
