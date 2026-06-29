from dataclasses import dataclass

@dataclass
class Attachment:
    filename: str
    filetype: str
    filepath: str
    exists: bool
