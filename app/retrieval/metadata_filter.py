"""
app/retrieval/metadata_filter.py — Converts user filter dicts into ChromaDB where clauses.

WHY THIS MODULE EXISTS
----------------------
ChromaDB's ``collection.query()`` accepts an optional ``where`` parameter
that narrows the search to documents matching certain metadata conditions.
The raw ChromaDB where-clause syntax is a dict of operator dicts, e.g.:
    {"source_chat": {"$eq": "Alice & Bob"}}

Callers of the retrieval pipeline should not need to know this syntax.
``MetadataFilter`` accepts a plain Python dict of ``{field: value}`` pairs
and produces the correct ChromaDB where clause.

It also:
  • Validates that every field name is one the store actually writes.
  • Validates that every value is a scalar type ChromaDB can filter on.
  • Rejects unknown fields immediately with a helpful error message.

SUPPORTED FIELDS
----------------
Only the scalar metadata fields written by Phase 4's ``_build_metadata``
are supported.  List fields (participants, message_ids, attachments) are
stored as JSON strings and cannot be filtered with equality operators —
those require application-level post-filtering in Phase 6.

SUPPORTED OPERATORS
-------------------
Simple equality filter:   {"source_chat": "Alice & Bob"}
Operator-style filter:    {"chunk_index": {"$gte": 5}}

Supported operators (subset of ChromaDB's $where):
  $eq   — equal (default for scalar values)
  $ne   — not equal
  $gt   — greater than   (int/float only)
  $gte  — greater or equal
  $lt   — less than
  $lte  — less or equal

CHROMADB WHERE CLAUSE RULES
----------------------------
  • Must be a flat dict — no nested $and/$or in this implementation.
  • If only one condition is provided, wrap it directly.
  • If multiple conditions are provided, wrap in {"$and": [...]}.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from exceptions.exceptions import MetadataFilterError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported metadata fields and their expected ChromaDB-compatible types
# ---------------------------------------------------------------------------
_SUPPORTED_FIELDS: Dict[str, type] = {
    "source_chat": str,
    "chunk_index": int,
    "token_count": int,
    "message_count": int,
    "attachment_count": int,
    "contains_images": bool,
    "contains_audio": bool,
    "contains_video": bool,
    "contains_documents": bool,
    "embedding_model": str,
    "schema_version": str,
}

# Supported comparison operators
_VALID_OPERATORS: frozenset = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte"})

# Operators valid only for numeric types
_NUMERIC_OPERATORS: frozenset = frozenset({"$gt", "$gte", "$lt", "$lte"})

# ChromaDB scalar value types
_SCALAR_TYPES = (str, int, float, bool)


class MetadataFilter:
    """
    Converts a plain Python filter dict into a ChromaDB ``where`` clause.

    Usage
    -----
    ::

        mf = MetadataFilter()
        where = mf.build({"source_chat": "Alice & Bob", "contains_images": True})
        # {"$and": [
        #     {"source_chat": {"$eq": "Alice & Bob"}},
        #     {"contains_images": {"$eq": True}},
        # ]}

        # Operator-style:
        where = mf.build({"chunk_index": {"$gte": 3}})
        # {"chunk_index": {"$gte": 3}}
    """

    def build(self, filters: Optional[Dict[str, Any]]) -> Optional[Dict]:
        """
        Build a ChromaDB ``where`` clause from *filters*.

        Args:
            filters: Dict of ``{field_name: value}`` or
                     ``{field_name: {"$op": value}}`` pairs.
                     Pass ``None`` or ``{}`` to get ``None`` back (no filter).

        Returns:
            ChromaDB-compatible ``where`` dict, or ``None`` when no filter
            should be applied.

        Raises:
            MetadataFilterError: If any field name is unsupported, any value
                                 is of an invalid type, or any operator is
                                 not recognised.
        """
        if not filters:
            return None

        if not isinstance(filters, dict):
            raise MetadataFilterError(
                f"filters must be a dict, got {type(filters).__name__}."
            )

        conditions: List[Dict] = []

        for field, value in filters.items():
            condition = self._build_condition(field, value)
            conditions.append(condition)

        if len(conditions) == 0:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_condition(field: str, value: Any) -> Dict:
        """
        Build a single ChromaDB condition for one field/value pair.

        Args:
            field: Metadata field name.
            value: Scalar value or operator dict.

        Returns:
            A ChromaDB condition dict.

        Raises:
            MetadataFilterError: On validation failure.
        """
        # Validate field name
        if field not in _SUPPORTED_FIELDS:
            raise MetadataFilterError(
                f"Unsupported metadata filter field: {field!r}.  "
                f"Supported fields: {sorted(_SUPPORTED_FIELDS.keys())}."
            )

        expected_type = _SUPPORTED_FIELDS[field]

        # Operator-style: {"$op": value}
        if isinstance(value, dict):
            return MetadataFilter._build_operator_condition(field, value, expected_type)

        # Simple equality: scalar value
        return MetadataFilter._build_equality_condition(field, value, expected_type)

    @staticmethod
    def _build_equality_condition(
        field: str, value: Any, expected_type: type
    ) -> Dict:
        """Build an equality (``$eq``) condition."""
        MetadataFilter._validate_scalar(field, value, expected_type)
        return {field: {"$eq": value}}

    @staticmethod
    def _build_operator_condition(
        field: str, op_dict: Dict, expected_type: type
    ) -> Dict:
        """Build an operator-style condition from a ``{"$op": value}`` dict."""
        if len(op_dict) != 1:
            raise MetadataFilterError(
                f"Operator dict for field {field!r} must contain exactly one "
                f"operator key, got {list(op_dict.keys())}."
            )

        operator, value = next(iter(op_dict.items()))

        if operator not in _VALID_OPERATORS:
            raise MetadataFilterError(
                f"Unsupported operator {operator!r} for field {field!r}.  "
                f"Supported operators: {sorted(_VALID_OPERATORS)}."
            )

        # Numeric-only operators require int or float
        if operator in _NUMERIC_OPERATORS and expected_type not in (int, float):
            raise MetadataFilterError(
                f"Operator {operator!r} is only valid for numeric fields, "
                f"but field {field!r} expects {expected_type.__name__}."
            )

        MetadataFilter._validate_scalar(field, value, expected_type)
        return {field: {operator: value}}

    @staticmethod
    def _validate_scalar(field: str, value: Any, expected_type: type) -> None:
        """
        Validate that *value* is a compatible ChromaDB scalar type.

        For bool fields, only bool is accepted.
        For int fields, int is accepted (not float — avoids ambiguity).
        For str fields, only str is accepted.

        Raises:
            MetadataFilterError: If the value type is incompatible.
        """
        if not isinstance(value, _SCALAR_TYPES):
            raise MetadataFilterError(
                f"Filter value for field {field!r} must be a scalar "
                f"(str, int, float, bool), got {type(value).__name__}."
            )

        # bool is a subclass of int in Python; check bool first
        if expected_type is bool and not isinstance(value, bool):
            raise MetadataFilterError(
                f"Field {field!r} expects a bool value, "
                f"got {type(value).__name__} ({value!r})."
            )

        if expected_type is int and not isinstance(value, (int, float)):
            raise MetadataFilterError(
                f"Field {field!r} expects a numeric value, "
                f"got {type(value).__name__} ({value!r})."
            )

        if expected_type is str and not isinstance(value, str):
            raise MetadataFilterError(
                f"Field {field!r} expects a str value, "
                f"got {type(value).__name__} ({value!r})."
            )

    @staticmethod
    def supported_fields() -> List[str]:
        """Return the sorted list of supported metadata field names."""
        return sorted(_SUPPORTED_FIELDS.keys())
