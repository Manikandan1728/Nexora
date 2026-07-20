"""
app/retrieval/query_scope_builder.py

[ADDITIVE] — Task 7, Requirement 6.

QueryScopeBuilder enforces server-side owner isolation. It:
  1. Forces effective.owner_id from the authenticated context — never client input.
  2. Validates that requested conversation_id(s) belong to the owner.
  3. Detects and rejects unsupported filter combinations.
  4. Produces an EffectiveMetadataFilter safe for ChromaWhereBuilder.

The conversation ownership registry is injected via IConversationOwnershipRegistry
so tests can use in-memory fakes without a real database.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from app.retrieval.effective_metadata_filter import EffectiveMetadataFilter
from exceptions.exceptions import (
    ConversationNotOwned,
    UnsupportedFilterCombination,
)

logger = logging.getLogger(__name__)


@runtime_checkable
class IConversationOwnershipRegistry(Protocol):
    """
    Minimal interface for checking conversation ownership.
    Implemented by real repositories and test fakes.
    """
    def is_conversation_owned_by(
        self, owner_id: str, conversation_id: str
    ) -> bool: ...


class AllConversationsOwnedRegistry:
    """
    Permissive registry for development / mock mode.
    Treats all conversations as belonging to any owner.
    Replace with a real registry in production.
    """
    def is_conversation_owned_by(
        self, owner_id: str, conversation_id: str
    ) -> bool:
        return True


class QueryScopeBuilder:
    """
    Builds an EffectiveMetadataFilter from a validated request filter dict,
    enforcing server-side owner isolation.

    Usage
    -----
    ::

        builder = QueryScopeBuilder(registry=my_registry)
        effective = builder.build(
            authenticated_owner_id="user_123",
            requested_filters={"source": "telegram",
                                "conversation_id": "tg_chat_anu_001"},
        )
    """

    def __init__(
        self,
        registry: IConversationOwnershipRegistry | None = None,
    ) -> None:
        self._registry = registry or AllConversationsOwnedRegistry()

    def build(
        self,
        authenticated_owner_id: str,
        requested_filters: dict | None,
    ) -> EffectiveMetadataFilter:
        """
        Produce an EffectiveMetadataFilter from raw request filters.

        Rules:
        - owner_id is ALWAYS taken from authenticated_owner_id, never filters.
        - Singular conversation_id and plural conversation_ids cannot both be set.
        - Singular content_type and plural content_types cannot both be set.
        - Every conversation_id must belong to authenticated_owner_id.

        Args:
            authenticated_owner_id: Owner from the auth context.
            requested_filters:      Raw filter dict from the client request.
                                    May be None or empty.

        Returns:
            EffectiveMetadataFilter ready for ChromaWhereBuilder.

        Raises:
            UnsupportedFilterCombination: On mutually exclusive filter pairs.
            ConversationNotOwned: If any conversation_id is not owned.
        """
        f = requested_filters or {}
        eff = EffectiveMetadataFilter(owner_id=authenticated_owner_id)

        # Source
        if "source" in f and f["source"]:
            eff.source = str(f["source"])

        # Source account
        if "source_account_id" in f and f["source_account_id"]:
            eff.source_account_id = str(f["source_account_id"])

        # Singular vs plural conversation
        has_singular = "conversation_id" in f and f["conversation_id"]
        has_plural   = "conversation_ids" in f and f["conversation_ids"]

        if has_singular and has_plural:
            raise UnsupportedFilterCombination(
                "Cannot supply both conversation_id and conversation_ids. "
                "Use conversation_id for a single chat or conversation_ids "
                "for multiple chats."
            )

        if has_singular:
            conv_id = str(f["conversation_id"])
            self._assert_owned(authenticated_owner_id, conv_id)
            eff.conversation_id = conv_id

        if has_plural:
            raw_ids = list(f["conversation_ids"])
            validated = []
            for cid in raw_ids:
                cid = str(cid)
                self._assert_owned(authenticated_owner_id, cid)
                validated.append(cid)
            eff.conversation_ids = validated

        # Sender
        if "sender_id" in f and f["sender_id"]:
            eff.sender_id = str(f["sender_id"])

        # Singular vs plural content_type
        has_ct  = "content_type" in f and f["content_type"]
        has_cts = "content_types" in f and f["content_types"]

        if has_ct and has_cts:
            raise UnsupportedFilterCombination(
                "Cannot supply both content_type and content_types."
            )

        if has_ct:
            eff.content_type = str(f["content_type"])
        if has_cts:
            eff.content_types = [str(x) for x in f["content_types"]]

        # Source message ID
        if "source_message_id" in f and f["source_message_id"]:
            eff.source_message_id = str(f["source_message_id"])

        # Timestamps (already validated as ISO strings by TelegramMetadataFilter)
        if "timestamp_from" in f and f["timestamp_from"]:
            eff.timestamp_from = str(f["timestamp_from"])
        if "timestamp_to" in f and f["timestamp_to"]:
            eff.timestamp_to = str(f["timestamp_to"])

        logger.info(
            "QueryScopeBuilder: owner=%r source=%r conv=%r sender=%r",
            authenticated_owner_id,
            eff.source,
            eff.conversation_id or eff.conversation_ids,
            eff.sender_id,
        )
        return eff

    def _assert_owned(self, owner_id: str, conversation_id: str) -> None:
        if not self._registry.is_conversation_owned_by(owner_id, conversation_id):
            raise ConversationNotOwned(
                f"Conversation {conversation_id!r} does not belong to "
                f"owner {owner_id!r}."
            )
