# utils/regex_patterns.py — Re-export from message_patterns.py.
# The canonical module is now utils/message_patterns.py.
# This file exists only for import compatibility during the transition.
from utils.message_patterns import (
    SENDER_MESSAGE_PATTERN,
    SYSTEM_MESSAGE_PATTERN,
    DATE_PATTERN,
    ATTACHMENT_PATTERN,
)

__all__ = [
    "SENDER_MESSAGE_PATTERN",
    "SYSTEM_MESSAGE_PATTERN",
    "DATE_PATTERN",
    "ATTACHMENT_PATTERN",
]
