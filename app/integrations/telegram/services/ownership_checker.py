"""
app/integrations/telegram/services/ownership_checker.py

[BREAKING-INTENTIONAL] — Replaces _AlwaysOwnedChecker.

Change Impact Analysis:
  _AlwaysOwnedChecker is the default in QueryScopeBuilder.__init__().
  It is used by:
    1. api/services/query_service.py — QueryScopeBuilder() with no arg
    2. api/routes/telegram.py — _process_events() → QueryScopeBuilder()
  Both callers will now receive DatabaseChatOwnershipChecker when this
  module is imported and injected. _AlwaysOwnedChecker remains available
  as a test stub but is no longer the production default.

  Rollback: Pass _AlwaysOwnedChecker() explicitly to QueryScopeBuilder()
  in query_service.py and telegram.py to restore permissive behavior.

Decision Record DR-1 (disabled-chat policy):
  A disabled (indexing_enabled=False) chat is STILL searchable for
  already-indexed data. The checker only rejects:
    - Chat not in DB (ConversationNotFound)
    - Chat owned by different owner (ConversationNotOwned)
    - Chat marked is_deleted=True (ConversationDeleted)
  It does NOT reject chats with indexing_enabled=False.

Decision Record DR-2 (sender-membership):
  Sender membership in groups is NOT validated here. The checker validates
  conversation ownership only. Sender filtering is a ChromaDB metadata
  concern. ISenderMembershipChecker is provided as a future extension point.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.retrieval.telegram_filter import IChatOwnershipChecker, ConversationNotOwned
from app.integrations.telegram.db.orm_models import TelegramDeletionTombstoneORM

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed ownership errors (Phase 5)
# ---------------------------------------------------------------------------

class TelegramConversationNotFoundError(Exception):
    """Requested conversation_id is not in the database."""
    def __init__(self, conversation_id: str):
        super().__init__(f"Telegram conversation not found: {conversation_id!r}")
        self.conversation_id = conversation_id


class TelegramConversationNotOwnedError(Exception):
    """Requested conversation belongs to a different owner."""
    def __init__(self, conversation_id: str):
        # Deliberately vague — do not disclose whether other owner has it
        super().__init__("Conversation not authorized for the authenticated user.")
        self.conversation_id = conversation_id


class TelegramConversationDeletedError(Exception):
    """Requested conversation has been soft-deleted."""
    def __init__(self, conversation_id: str):
        super().__init__("Conversation not available.")
        self.conversation_id = conversation_id


class TelegramAccountNotOwnedError(Exception):
    """Requested Telegram account belongs to a different owner."""
    def __init__(self, account_id: str):
        super().__init__("Telegram account not authorized.")
        self.account_id = account_id


class TelegramConversationScopeMismatchError(Exception):
    """Conversation exists but belongs to a different account than specified."""
    def __init__(self, conversation_id: str):
        super().__init__("Conversation scope mismatch.")
        self.conversation_id = conversation_id


class TelegramSenderScopeError(Exception):
    """Sender is not validated for the selected conversation (future use)."""
    def __init__(self, sender_id: str, conversation_id: str):
        super().__init__("Sender not in scope for the selected conversation.")
        self.sender_id = sender_id
        self.conversation_id = conversation_id


# ---------------------------------------------------------------------------
# DB-backed ownership checker
# ---------------------------------------------------------------------------

class DatabaseChatOwnershipChecker(IChatOwnershipChecker):
    """
    DB-backed implementation of IChatOwnershipChecker.

    Uses SqliteTelegramChatRepository to validate every requested
    conversation_id against the database.

    Contract (replacing _AlwaysOwnedChecker):
      BEFORE: is_owned() always returned True.
      AFTER:  is_owned() returns True only when:
                - chat.owner_id == authenticated_owner_id
                - chat.is_deleted == False
              Returns False (and logs) for unknown or unauthorized chats.

    Callers affected:
      - QueryScopeBuilder.build() — raises ConversationNotOwned on False
      - api/services/query_service.py — inherits via QueryScopeBuilder
      - api/routes/telegram.py — inherits via QueryScopeBuilder

    The checker does NOT raise directly — it returns bool.
    QueryScopeBuilder converts False → ConversationNotOwned exception.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def is_owned(self, owner_id: str, conversation_id: str) -> bool:
        """
        Return True when conversation_id exists, belongs to owner_id,
        and is not soft-deleted.

        Does NOT check indexing_enabled (DR-1: disabled chats stay searchable).
        """
        from app.integrations.telegram.repositories.chat_repo import SqliteTelegramChatRepository
        repo = SqliteTelegramChatRepository()

        # We don't have source_account_id in this context, so search by
        # owner_id + telegram_chat_id only (no account filter needed here
        # since the uniqueness constraint is per account, not global).
        # Use a broader query: any non-deleted chat for this owner with this ID.
        from app.integrations.telegram.db.orm_models import TelegramChatORM
        chat = (
            self._session.query(TelegramChatORM)
            .filter(
                TelegramChatORM.owner_id == owner_id,
                TelegramChatORM.telegram_chat_id == conversation_id,
                TelegramChatORM.is_deleted == False,
            )
            .first()
        )
        if chat is None:
            logger.info(
                "OwnershipChecker: conv=%r not found for owner=%r",
                conversation_id, owner_id,
            )
            return False
        return True

    def is_owned_with_detail(
        self, owner_id: str, conversation_id: str
    ) -> tuple[bool, str]:
        """Returns (is_owned, reason) for structured error reporting."""
        from app.integrations.telegram.db.orm_models import TelegramChatORM

        # Check if chat exists at all (any owner)
        any_chat = (
            self._session.query(TelegramChatORM)
            .filter(TelegramChatORM.telegram_chat_id == conversation_id)
            .first()
        )
        if any_chat is None:
            return False, "not_found"
        if any_chat.is_deleted:
            return False, "deleted"
        if any_chat.owner_id != owner_id:
            return False, "not_owned"
        return True, "ok"


# ---------------------------------------------------------------------------
# ISenderMembershipChecker — future extension point (DR-2)
# ---------------------------------------------------------------------------

@runtime_checkable
class ISenderMembershipChecker(Protocol):
    """
    Future interface for validating sender membership in a group.
    Not implemented in this milestone (no live Telegram data available).
    """
    def is_member(self, owner_id: str, conversation_id: str, sender_id: str) -> bool: ...


class _UnvalidatedSenderChecker:
    """
    Stub: sender membership is not validated (DR-2).
    Always returns True with a log warning.
    """
    def is_member(self, owner_id: str, conversation_id: str, sender_id: str) -> bool:
        logger.debug(
            "SenderMembership: not validated (stub) conv=%r sender=%r",
            conversation_id, sender_id,
        )
        return True
