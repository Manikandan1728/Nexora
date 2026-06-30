class InvalidInputError(Exception):
    """
    Raised when the input path is invalid.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ZipValidationError(Exception):
    """
    Raised when ZIP validation fails.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ExtractionError(Exception):
    """
    Raised when extraction of ZIP files fails.
    """
    def __init__(self, message: str):
        super().__init__(message)

class DatasetValidationError(Exception):
    """
    Raised when dataset validation fails.
    """
    def __init__(self, message: str):
        super().__init__(message)

class ParsingError(Exception):
    """
    Raised when parsing fails.
    """
    def __init__(self, message: str):
        super().__init__(message)


class TokenizationError(Exception):
    """
    Raised when the tokenizer service encounters an unrecoverable error
    (e.g. the model weights cannot be loaded, or a message cannot be
    encoded).
    """
    def __init__(self, message: str):
        super().__init__(message)


class ChunkingError(Exception):
    """
    Raised when the chunker cannot produce a valid chunk list from the
    supplied messages (e.g. empty input, or a single message whose text
    cannot be split at sentence boundaries within the token limit).
    """
    def __init__(self, message: str):
        super().__init__(message)


class DocumentBuildError(Exception):
    """
    Raised when the document builder fails to construct a Document from
    a message chunk (e.g. missing required fields, invalid timestamps).
    """
    def __init__(self, message: str):
        super().__init__(message)
