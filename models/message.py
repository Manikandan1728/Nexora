from dataclasses import dataclass

@dataclass
class Message:
    id: int
    timestamp: str
    sender: str
    message: str
    message_type: str
    attachment: str = None
