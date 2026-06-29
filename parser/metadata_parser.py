from typing import List
from models.message import Message
from models.metadata import ChatMetadata
from exceptions.exceptions import ParsingError


class MetadataParser:
    """
    Extracts metadata from a list of parsed WhatsApp messages.
    """

    def __init__(self, messages: List[Message]):
        self.messages = messages

    def parse_metadata(self) -> ChatMetadata:
        """
        Computes and returns a ChatMetadata object from the message list.
        Raises ParsingError if the message list is empty.
        """
        if not self.messages:
            raise ParsingError("Cannot extract metadata: message list is empty.")

        # Exclude SYSTEM messages from participant discovery
        participants: List[str] = sorted(
            {msg.sender for msg in self.messages if msg.sender != 'SYSTEM'}
        )

        chat_start_date: str = self.messages[0].timestamp
        chat_end_date: str = self.messages[-1].timestamp

        total_messages: int = len(self.messages)
        attachment_count: int = sum(
            1 for msg in self.messages if msg.message_type == 'attachment'
        )

        return ChatMetadata(
            total_messages=total_messages,
            participants=participants,
            chat_start_date=chat_start_date,
            chat_end_date=chat_end_date,
            attachment_count=attachment_count,
        )
