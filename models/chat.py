from dataclasses import dataclass
from typing import List
from .message import Message
from .attachment import Attachment

@dataclass
class Chat:
    participants: List[str]
    messages: List[Message]
    metadata: dict
