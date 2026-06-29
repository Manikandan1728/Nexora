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
