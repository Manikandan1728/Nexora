import re

# ---------------------------------------------------------------------------
# WhatsApp message line patterns
# ---------------------------------------------------------------------------
# WhatsApp exports timestamps in one of two forms:
#   12-hour:  "12/31/2023, 9:05 AM"   (with AM/PM)
#   24-hour:  "31/12/2023, 21:05"     (no AM/PM)
#
# Both day-first and month-first orderings are used depending on the device
# locale, so the pattern accepts both.
#
# Named groups make extraction unambiguous regardless of AM/PM presence:
#   - timestamp  : full date+time string
#   - sender     : the display name / phone number
#   - body       : everything after "Sender: "

_TIMESTAMP = r'(?P<timestamp>\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?:\s*[AP]M)?)'

# Full user message:  "<timestamp> - <sender>: <body>"
SENDER_MESSAGE_PATTERN = re.compile(
    r'^' + _TIMESTAMP + r'\s*-\s*(?P<sender>[^:]+?):\s*(?P<body>.*)$'
)

# System / event message (no "Sender:" part):
#   "<timestamp> - <body>"  where body does NOT contain ":"
#   e.g. "Messages and calls are end-to-end encrypted."
SYSTEM_MESSAGE_PATTERN = re.compile(
    r'^' + _TIMESTAMP + r'\s*-\s*(?P<body>.+)$'
)

# Standalone timestamp check (first characters of a new message line)
DATE_PATTERN = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}')

# WhatsApp omitted-media placeholder
ATTACHMENT_PATTERN = re.compile(
    r'(?P<filetype>image|video|audio|document|sticker)\s+omitted',
    re.IGNORECASE,
)
