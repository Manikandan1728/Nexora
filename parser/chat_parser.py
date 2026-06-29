import re
from typing import List
from models.message import Message
from utils.regex_patterns import SENDER_MESSAGE_PATTERN, SYSTEM_MESSAGE_PATTERN
from exceptions.exceptions import ParsingError


class ChatParser:
    """
    Parses WhatsApp chat text to extract individual messages.
    """

    def __init__(self, chat_text: str):
        self.chat_text = chat_text

    def parse_messages(self) -> List[Message]:
        """
        Parses the chat text and returns a list of Message objects.

        WhatsApp exports two line formats:
          1. Regular message:
             DD/MM/YYYY, HH:MM - Sender: body
          2. System event (no sender):
             DD/MM/YYYY, HH:MM - Messages and calls are end-to-end encrypted...

        Multi-line messages are joined to the preceding message body.
        Raises ParsingError if the text is empty or entirely unparseable.
        """
        if not self.chat_text or not self.chat_text.strip():
            raise ParsingError("Chat text is empty; cannot parse messages.")

        messages: List[Message] = []
        current_parts: dict | None = None

        for raw_line in self.chat_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = SENDER_MESSAGE_PATTERN.match(line)
            if match:
                # Commit the previous accumulated message
                if current_parts is not None:
                    messages.append(self._build_message(len(messages) + 1, current_parts))

                current_parts = {
                    'timestamp': match.group('timestamp'),
                    'sender': match.group('sender'),
                    'body': match.group('body'),
                }
            else:
                system_match = SYSTEM_MESSAGE_PATTERN.match(line)
                if system_match:
                    # Commit previous, then record a system message
                    if current_parts is not None:
                        messages.append(self._build_message(len(messages) + 1, current_parts))
                    current_parts = {
                        'timestamp': system_match.group('timestamp'),
                        'sender': 'SYSTEM',
                        'body': system_match.group('body'),
                    }
                elif current_parts is not None:
                    # Continuation line of the previous message
                    current_parts['body'] += '\n' + line

        # Commit the last buffered message
        if current_parts is not None:
            messages.append(self._build_message(len(messages) + 1, current_parts))

        return messages

    @staticmethod
    def _build_message(msg_id: int, parts: dict) -> Message:
        """Constructs a Message from accumulated line parts."""
        body = parts['body']
        attachment_ref: str | None = None

        # Detect WhatsApp attachment placeholder patterns
        attach_match = re.search(r'<(.+?)>\s*\(file attached\)', body)
        if attach_match:
            attachment_ref = attach_match.group(1)
            message_type = 'attachment'
        elif re.search(r'(image|video|audio|document|sticker) omitted', body, re.IGNORECASE):
            attachment_ref = body.strip()
            message_type = 'attachment'
        else:
            message_type = 'text'

        return Message(
            id=msg_id,
            timestamp=parts['timestamp'],
            sender=parts['sender'],
            message=body,
            message_type=message_type,
            attachment=attachment_ref,
        )
