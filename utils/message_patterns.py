"""
utils/message_patterns.py — Regex patterns for timestamped chat message lines.

These patterns match the common exported-chat text format used by many
messaging platforms:

    D/M/YYYY, H:MM AM/PM - Sender: body
    D/M/YYYY, H:MM - body                (system/event message)

Both 12-hour (AM/PM) and 24-hour formats are supported.
Both day-first and month-first orderings are accepted.

Named groups:
  - timestamp  : full date+time string
  - sender     : display name or phone number
  - body       : message content after "Sender: "
"""

import re

_TIMESTAMP = r'(?P<timestamp>\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?:\s*[AP]M)?)'

# Full user message:  "<timestamp> - <sender>: <body>"
SENDER_MESSAGE_PATTERN = re.compile(
    r'^' + _TIMESTAMP + r'\s*-\s*(?P<sender>[^:]+?):\s*(?P<body>.*)$'
)

# System / event message (no "Sender:" part):
#   "<timestamp> - <body>"
SYSTEM_MESSAGE_PATTERN = re.compile(
    r'^' + _TIMESTAMP + r'\s*-\s*(?P<body>.+)$'
)

# Standalone timestamp check (first characters of a new message line)
DATE_PATTERN = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}')

# Media omission placeholder (generic, not source-specific)
ATTACHMENT_PATTERN = re.compile(
    r'(?P<filetype>image|video|audio|document|sticker)\s+omitted',
    re.IGNORECASE,
)
