"""
app/retrieval/effective_metadata_filter.py

[ADDITIVE] — Task 6, Requirement 5 & 6.

EffectiveMetadataFilter is the server-side, owner-locked, validated
representation of a query's scope. It is produced by QueryScopeBuilder
and consumed exclusively by ChromaWhereBuilder.

No client-supplied value may appear here without server-side validation.
owner_id is ALWAYS set from the authenticated context, never from the
client request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EffectiveMetadataFilter:
    """
    Server-validated, owner-locked filter passed to ChromaWhereBuilder.

    owner_id is always set by QueryScopeBuilder from the authenticated
    context — never from client input.

    conversation_ids is used for multi-conversation queries.
    If conversation_id is set, conversation_ids is ignored (singular
    takes precedence, enforced by QueryScopeBuilder).
    """
    # Mandatory — always set by QueryScopeBuilder
    owner_id: str

    # Optional scope narrowers (all server-validated)
    source: Optional[str] = None
    source_account_id: Optional[str] = None
    conversation_id: Optional[str] = None       # single conversation
    conversation_ids: Optional[list[str]] = None  # multi-conversation
    sender_id: Optional[str] = None
    content_type: Optional[str] = None
    content_types: Optional[list[str]] = None
    source_message_id: Optional[str] = None

    # Timestamp range (ISO-8601 strings after validation)
    timestamp_from: Optional[str] = None
    timestamp_to: Optional[str] = None
