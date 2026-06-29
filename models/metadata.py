from dataclasses import dataclass

@dataclass
class ChatMetadata:
    total_messages: int
    participants: list
    chat_start_date: str
    chat_end_date: str
    attachment_count: int
