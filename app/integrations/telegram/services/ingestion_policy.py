"""
app/integrations/telegram/services/ingestion_policy.py

[ADDITIVE] — New file. No existing code is modified.

TelegramIngestionPolicy decides whether a KnowledgeObject should be
processed, ignored, or handled as an edit/delete.

RULES (in evaluation order)
----------------------------
1. The source account must belong to the requesting owner.
2. The chat must have indexing_enabled = True.
3. The message timestamp must be >= indexing_enabled_at.
4. The message must not be a duplicate (already processed with status=COMPLETED).
5. Deleted messages → PROCESS_DELETE (triggers deletion from index).
6. Edited messages → PROCESS_EDIT (triggers re-indexing).
7. All other messages → PROCESS.

Each rule produces a clear decision with a human-readable reason,
making policy decisions auditable and testable without mocking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

from models.knowledge_object import KnowledgeObject


class IngestionAction(str, Enum):
    """What the pipeline should do with a KnowledgeObject."""
    PROCESS        = "process"         # Normal indexing
    PROCESS_EDIT   = "process_edit"    # Re-index after edit
    PROCESS_DELETE = "process_delete"  # Remove from index
    IGNORE         = "ignore"          # Skip entirely


@dataclass(frozen=True)
class IngestionDecision:
    """
    The output of TelegramIngestionPolicy.decide().

    Attributes
    ----------
    action : IngestionAction
        What should happen with this KnowledgeObject.
    reason : str
        Human-readable explanation. Always present for auditing.
    """
    action: IngestionAction
    reason: str

    @property
    def should_process(self) -> bool:
        return self.action in (IngestionAction.PROCESS, IngestionAction.PROCESS_EDIT)

    @property
    def should_delete(self) -> bool:
        return self.action == IngestionAction.PROCESS_DELETE

    @property
    def should_ignore(self) -> bool:
        return self.action == IngestionAction.IGNORE


@runtime_checkable
class IChatConfigProvider(Protocol):
    """
    Interface for providing per-chat configuration.
    Implemented by the real repository and by test fakes.
    """
    def is_indexing_enabled(self, owner_id: str, conversation_id: str) -> bool: ...
    def get_indexing_enabled_at(self, owner_id: str, conversation_id: str) -> datetime | None: ...
    def is_account_owner(self, owner_id: str, source_account_id: str) -> bool: ...


@runtime_checkable
class IProcessingStateProvider(Protocol):
    """
    Interface for checking whether a message was already processed.
    Used for idempotency.
    """
    def is_already_processed(
        self,
        source_account_id: str,
        conversation_id: str,
        source_message_id: str,
    ) -> bool: ...


class TelegramIngestionPolicy:
    """
    Evaluates each KnowledgeObject against ingestion rules and returns
    an IngestionDecision.

    Designed for dependency injection: both config_provider and
    state_provider are interfaces, making this fully testable without
    a real database.

    Usage
    -----
    ::

        policy = TelegramIngestionPolicy(
            config_provider=my_chat_config,
            state_provider=my_processing_state,
        )
        decision = policy.decide(knowledge_object)
        if decision.should_process:
            pipeline.run(knowledge_object)
    """

    def __init__(
        self,
        config_provider: IChatConfigProvider,
        state_provider: IProcessingStateProvider,
    ) -> None:
        self._config = config_provider
        self._state = state_provider

    def decide(self, obj: KnowledgeObject) -> IngestionDecision:
        """
        Evaluate one KnowledgeObject against all ingestion rules.

        Rules are checked in order; the first matching rule wins.

        Args:
            obj: A KnowledgeObject produced by TelegramNormalizer.

        Returns:
            IngestionDecision with action and reason.
        """
        # Rule 1: Account ownership
        if not self._config.is_account_owner(obj.owner_id, obj.source_account_id):
            return IngestionDecision(
                action=IngestionAction.IGNORE,
                reason=f"Account {obj.source_account_id!r} does not belong to owner {obj.owner_id!r}.",
            )

        # Rule 2: Indexing must be enabled for this chat
        if not self._config.is_indexing_enabled(obj.owner_id, obj.conversation_id):
            return IngestionDecision(
                action=IngestionAction.IGNORE,
                reason=f"Indexing is disabled for chat {obj.conversation_id!r}.",
            )

        # Rule 3: Message must be after the activation timestamp
        enabled_at = self._config.get_indexing_enabled_at(obj.owner_id, obj.conversation_id)
        if enabled_at is not None:
            # Make both timezone-aware for comparison
            msg_ts = obj.timestamp
            if msg_ts.tzinfo is None:
                msg_ts = msg_ts.replace(tzinfo=timezone.utc)
            if enabled_at.tzinfo is None:
                enabled_at = enabled_at.replace(tzinfo=timezone.utc)
            if msg_ts < enabled_at:
                return IngestionDecision(
                    action=IngestionAction.IGNORE,
                    reason=(
                        f"Message timestamp {msg_ts.isoformat()} is before "
                        f"indexing activation time {enabled_at.isoformat()}."
                    ),
                )

        # Rule 4: Deleted messages → delete from index
        if obj.is_deleted:
            return IngestionDecision(
                action=IngestionAction.PROCESS_DELETE,
                reason=f"Message {obj.source_message_id!r} is marked deleted.",
            )

        # Rule 5: Duplicate check (already fully processed, not an edit)
        if not obj.is_edited and self._state.is_already_processed(
            obj.source_account_id,
            obj.conversation_id,
            obj.source_message_id,
        ):
            return IngestionDecision(
                action=IngestionAction.IGNORE,
                reason=(
                    f"Message {obj.source_message_id!r} was already processed "
                    f"(idempotency check)."
                ),
            )

        # Rule 6: Edited messages → re-index
        if obj.is_edited:
            return IngestionDecision(
                action=IngestionAction.PROCESS_EDIT,
                reason=f"Message {obj.source_message_id!r} is an edit; re-indexing.",
            )

        # Rule 7: Normal new message
        return IngestionDecision(
            action=IngestionAction.PROCESS,
            reason=f"Message {obj.source_message_id!r} accepted for indexing.",
        )
