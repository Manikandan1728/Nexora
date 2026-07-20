"""
app/retrieval/telegram_filter.py

[ADDITIVE] — New file. Extends the metadata filter schema with Telegram
identity fields, validated EffectiveMetadataFilter, and typed errors.

Requirements: 5, 6, 7, 18.

ChromaDB version verified: 1.5.9
Supported operators confirmed: $eq, $ne, $gt, $gte, $lt, $lte, $and, $or, $in
Timestamp range filtering: $gte/$lte on ISO-8601 strings is NOT reliable for
string comparison in ChromaDB (lexicographic, not chronological for all
formats). Application-level post-filter is applied after retrieval.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

from models.knowledge_object import SUPPORTED_CONTENT_TYPES
from exceptions.exceptions import MetadataFilterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# New typed exceptions (Requirements 18)
# ---------------------------------------------------------------------------

class UnauthorizedOwnerScope(Exception):
    """Client-supplied owner_id does not match authenticated owner."""
    def __init__(self, msg: str = "Unauthorized owner scope."):
        super().__init__(msg)

class ConversationNotFound(Exception):
    """Requested conversation_id does not exist."""
    def __init__(self, msg: str):
        super().__init__(msg)

class ConversationNotOwned(Exception):
    """Requested conversation_id is not owned by the authenticated user."""
    def __init__(self, msg: str):
        super().__init__(msg)

class InvalidSenderFilter(Exception):
    """sender_id invalid for the selected conversation."""
    def __init__(self, msg: str):
        super().__init__(msg)

class UnsupportedFilterCombination(Exception):
    """Filter combination is logically contradictory or unsupported."""
    def __init__(self, msg: str):
        super().__init__(msg)

class InvalidTimestampFilter(Exception):
    """Timestamp filter value is malformed."""
    def __init__(self, msg: str):
        super().__init__(msg)

class VectorFilterBuildError(Exception):
    """ChromaDB where-clause construction failed."""
    def __init__(self, msg: str):
        super().__init__(msg)

class MissingMandatoryMetadata(Exception):
    """Required metadata field missing at vector-store write time."""
    def __init__(self, msg: str):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# TelegramMetadataFilter — validated request-side filter model
# ---------------------------------------------------------------------------

@dataclass
class TelegramMetadataFilter:
    """
    Extended metadata filter supporting all Telegram identity fields.
    Validated before reaching ChromaDB — never passed raw from the client.

    All fields are optional. Empty strings are treated as "not supplied"
    and rejected with InvalidTimestampFilter / MetadataFilterError when
    semantically invalid.
    """
    # --- Existing legacy fields (preserved unchanged) ---
    source_chat:        Optional[str]  = None
    chunk_index:        Optional[int]  = None
    token_count:        Optional[int]  = None
    message_count:      Optional[int]  = None
    attachment_count:   Optional[int]  = None
    contains_images:    Optional[bool] = None
    contains_audio:     Optional[bool] = None
    contains_video:     Optional[bool] = None
    contains_documents: Optional[bool] = None
    embedding_model:    Optional[str]  = None
    schema_version:     Optional[str]  = None

    # --- New Telegram identity fields ---
    owner_id:           Optional[str]  = None
    source:             Optional[str]  = None
    source_account_id:  Optional[str]  = None
    conversation_id:    Optional[str]  = None
    conversation_ids:   Optional[List[str]] = None   # multi-conversation
    sender_id:          Optional[str]  = None
    content_type:       Optional[str]  = None
    content_types:      Optional[List[str]] = None   # multi-content-type
    source_message_id:  Optional[str]  = None
    timestamp_from:     Optional[str]  = None        # ISO-8601
    timestamp_to:       Optional[str]  = None        # ISO-8601

    def validate(self) -> "TelegramMetadataFilter":
        """
        Validate all supplied fields. Returns self on success.
        Raises MetadataFilterError, InvalidTimestampFilter, or
        UnsupportedFilterCombination on failure.
        """
        # Empty-string rejection for identifier fields
        for fname in ("owner_id", "source", "source_account_id",
                      "conversation_id", "sender_id", "source_message_id"):
            v = getattr(self, fname)
            if v is not None and not str(v).strip():
                raise MetadataFilterError(
                    f"Filter field '{fname}' must not be an empty string."
                )

        # Singular/plural conflict
        if self.conversation_id and self.conversation_ids:
            raise UnsupportedFilterCombination(
                "Supply either 'conversation_id' or 'conversation_ids', not both."
            )
        if self.content_type and self.content_types:
            raise UnsupportedFilterCombination(
                "Supply either 'content_type' or 'content_types', not both."
            )

        # Validate content_type values
        for ct_field, ct_val in [("content_type", self.content_type)]:
            if ct_val and ct_val not in SUPPORTED_CONTENT_TYPES:
                raise MetadataFilterError(
                    f"Unsupported content_type '{ct_val}'. "
                    f"Supported: {sorted(SUPPORTED_CONTENT_TYPES)}"
                )
        if self.content_types:
            for ct in self.content_types:
                if ct not in SUPPORTED_CONTENT_TYPES:
                    raise MetadataFilterError(
                        f"Unsupported content_type '{ct}' in content_types. "
                        f"Supported: {sorted(SUPPORTED_CONTENT_TYPES)}"
                    )

        # Validate conversation_ids list
        if self.conversation_ids:
            for cid in self.conversation_ids:
                if not cid or not cid.strip():
                    raise MetadataFilterError(
                        "conversation_ids must not contain empty strings."
                    )

        # Validate timestamp fields
        for ts_field in ("timestamp_from", "timestamp_to"):
            ts_val = getattr(self, ts_field)
            if ts_val is not None:
                _parse_iso_timestamp(ts_val, ts_field)

        return self


# ---------------------------------------------------------------------------
# EffectiveMetadataFilter — server-side, owner-enforced filter
# ---------------------------------------------------------------------------

@dataclass
class EffectiveMetadataFilter:
    """
    Server-enforced filter with owner_id guaranteed from authenticated context.
    Only ChromaWhereBuilder may consume this — never pass to client.
    """
    owner_id:           str                    # ALWAYS from authenticated context
    source:             Optional[str]  = None
    source_account_id:  Optional[str]  = None
    conversation_id:    Optional[str]  = None
    conversation_ids:   Optional[List[str]] = None
    sender_id:          Optional[str]  = None
    content_type:       Optional[str]  = None
    content_types:      Optional[List[str]] = None
    source_message_id:  Optional[str]  = None
    timestamp_from:     Optional[datetime] = None
    timestamp_to:       Optional[datetime] = None
    # Legacy fields passed through unchanged
    legacy_filters:     dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# QueryScopeBuilder — Requirement 6
# ---------------------------------------------------------------------------

class QueryScopeBuilder:
    """
    Builds an EffectiveMetadataFilter by enforcing owner_id from the
    authenticated context — never from client input.

    The owner_id in the returned EffectiveMetadataFilter is ALWAYS the
    authenticated_owner_id. Any client-supplied owner_id in requested_filters
    is silently overridden (not a security error — just ignored).

    Conversation ownership validation uses an injected IChatOwnershipChecker.
    In the current mock stage, all conversations are assumed to belong to the
    authenticated owner (no real DB yet). A real implementation would query
    TelegramChat records.
    """

    def __init__(self, ownership_checker: "IChatOwnershipChecker | None" = None):
        self._checker = ownership_checker or _AlwaysOwnedChecker()

    def build(
        self,
        authenticated_owner_id: str,
        requested_filters: TelegramMetadataFilter,
    ) -> EffectiveMetadataFilter:
        """
        Build a server-enforced EffectiveMetadataFilter.

        Args:
            authenticated_owner_id: Owner from trusted auth context (never client).
            requested_filters:      Validated TelegramMetadataFilter from request.

        Returns:
            EffectiveMetadataFilter with owner_id guaranteed from auth context.

        Raises:
            ConversationNotOwned: If a requested conversation_id is not owned.
            UnauthorizedOwnerScope: (reserved for future explicit owner_id check)
        """
        # Validate requested conversations belong to this owner
        if requested_filters.conversation_id:
            if not self._checker.is_owned(
                authenticated_owner_id, requested_filters.conversation_id
            ):
                raise ConversationNotOwned(
                    f"Conversation '{requested_filters.conversation_id}' "
                    f"is not owned by the authenticated user."
                )

        if requested_filters.conversation_ids:
            for cid in requested_filters.conversation_ids:
                if not self._checker.is_owned(authenticated_owner_id, cid):
                    raise ConversationNotOwned(
                        f"Conversation '{cid}' is not owned by the authenticated user."
                    )

        # Parse timestamp strings to datetime objects
        ts_from = (
            _parse_iso_timestamp(requested_filters.timestamp_from, "timestamp_from")
            if requested_filters.timestamp_from else None
        )
        ts_to = (
            _parse_iso_timestamp(requested_filters.timestamp_to, "timestamp_to")
            if requested_filters.timestamp_to else None
        )

        # Extract legacy fields (source_chat, chunk_index, etc.)
        legacy: dict[str, Any] = {}
        for fname in ("source_chat", "chunk_index", "token_count", "message_count",
                      "attachment_count", "contains_images", "contains_audio",
                      "contains_video", "contains_documents", "embedding_model",
                      "schema_version"):
            v = getattr(requested_filters, fname)
            if v is not None:
                legacy[fname] = v

        effective = EffectiveMetadataFilter(
            owner_id=authenticated_owner_id,  # ALWAYS from auth, never client
            source=requested_filters.source,
            source_account_id=requested_filters.source_account_id,
            conversation_id=requested_filters.conversation_id,
            conversation_ids=requested_filters.conversation_ids,
            sender_id=requested_filters.sender_id,
            content_type=requested_filters.content_type,
            content_types=requested_filters.content_types,
            source_message_id=requested_filters.source_message_id,
            timestamp_from=ts_from,
            timestamp_to=ts_to,
            legacy_filters=legacy,
        )

        logger.info(
            "QueryScopeBuilder: scope built owner=%r source=%r conv=%r sender=%r",
            authenticated_owner_id,
            effective.source,
            effective.conversation_id or effective.conversation_ids,
            effective.sender_id,
        )
        return effective


# ---------------------------------------------------------------------------
# ChromaWhereBuilder — Requirement 7
# ---------------------------------------------------------------------------

class ChromaWhereBuilder:
    """
    Translates an EffectiveMetadataFilter into a ChromaDB where-clause dict.

    ChromaDB 1.5.9 verified operators: $eq, $ne, $gt, $gte, $lt, $lte,
    $and, $or, $in.

    Timestamp range note: ChromaDB 1.5.9 stores metadata as flat scalars.
    ISO-8601 strings are compared lexicographically which is only correct
    for UTC timestamps with consistent format. This builder applies a
    string $gte/$lte prefilter when timestamps are supplied, AND the caller
    (query_service) must apply an application-level post-filter using the
    actual datetime objects for correctness. This limitation is documented.
    """

    def build(self, filters: EffectiveMetadataFilter) -> dict[str, Any] | None:
        """
        Build a ChromaDB where clause from an EffectiveMetadataFilter.

        Args:
            filters: Server-enforced filter (owner_id always present).

        Returns:
            ChromaDB where-clause dict, or None if no filters apply beyond owner.

        Raises:
            VectorFilterBuildError: If clause construction fails.
        """
        try:
            conditions: list[dict] = []

            # owner_id is ALWAYS the first and mandatory condition
            conditions.append({"owner_id": {"$eq": filters.owner_id}})

            # source
            if filters.source:
                conditions.append({"source": {"$eq": filters.source}})

            # source_account_id
            if filters.source_account_id:
                conditions.append({"source_account_id": {"$eq": filters.source_account_id}})

            # conversation_id (singular)
            if filters.conversation_id:
                conditions.append({"conversation_id": {"$eq": filters.conversation_id}})

            # conversation_ids (multi) — uses $in (confirmed supported in ChromaDB 1.5.9)
            elif filters.conversation_ids and len(filters.conversation_ids) > 1:
                conditions.append({"conversation_id": {"$in": filters.conversation_ids}})
            elif filters.conversation_ids and len(filters.conversation_ids) == 1:
                conditions.append({"conversation_id": {"$eq": filters.conversation_ids[0]}})

            # sender_id
            if filters.sender_id:
                conditions.append({"sender_id": {"$eq": filters.sender_id}})

            # content_type (singular)
            if filters.content_type:
                conditions.append({"content_type": {"$eq": filters.content_type}})

            # content_types (multi)
            elif filters.content_types and len(filters.content_types) > 1:
                conditions.append({"content_type": {"$in": filters.content_types}})
            elif filters.content_types and len(filters.content_types) == 1:
                conditions.append({"content_type": {"$eq": filters.content_types[0]}})

            # source_message_id
            if filters.source_message_id:
                conditions.append({"source_message_id": {"$eq": filters.source_message_id}})

            # Timestamp prefilter (string-lexicographic, UTC ISO-8601)
            # LIMITATION: Only accurate for UTC ISO-8601 with consistent format.
            # Application-level post-filter must be applied by the caller.
            if filters.timestamp_from:
                conditions.append({"timestamp": {"$gte": filters.timestamp_from.isoformat()}})
            if filters.timestamp_to:
                conditions.append({"timestamp": {"$lte": filters.timestamp_to.isoformat()}})

            # Legacy filter fields (source_chat, chunk_index, etc.)
            for fname, fval in filters.legacy_filters.items():
                if isinstance(fval, dict):
                    # Operator-style
                    conditions.append({fname: fval})
                else:
                    conditions.append({fname: {"$eq": fval}})

            if len(conditions) == 0:
                return None
            if len(conditions) == 1:
                return conditions[0]
            return {"$and": conditions}

        except (VectorFilterBuildError, ValueError, TypeError):
            raise
        except Exception as exc:
            raise VectorFilterBuildError(
                f"Failed to build ChromaDB where clause: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Interfaces and stubs
# ---------------------------------------------------------------------------

class IChatOwnershipChecker:
    """Checks whether a conversation belongs to an owner."""
    def is_owned(self, owner_id: str, conversation_id: str) -> bool:
        raise NotImplementedError


class _AlwaysOwnedChecker(IChatOwnershipChecker):
    """
    Stub implementation: all conversations assumed owned.
    Replace with a real DB-backed checker in production.
    """
    def is_owned(self, owner_id: str, conversation_id: str) -> bool:
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso_timestamp(value: str, field_name: str) -> datetime:
    """
    Parse an ISO-8601 timestamp string to a timezone-aware datetime.

    Raises:
        InvalidTimestampFilter: If parsing fails.
    """
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        raise InvalidTimestampFilter(
            f"Filter field '{field_name}' has an invalid timestamp value "
            f"'{value}'. Expected ISO-8601 format (e.g. '2026-07-13T18:30:00+05:30')."
        ) from exc
