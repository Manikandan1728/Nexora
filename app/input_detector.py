import os
from pathlib import Path
from exceptions.exceptions import InvalidInputError


class InputDetector:
    """
    Detects whether the input is a ZIP file or a folder.
    """

    @staticmethod
    def detect_input_type(input_path: str) -> str:
        """
        Accepts a path and detects whether it is a ZIP file or a folder.
        Raises InvalidInputError for invalid input.
        """
        path = Path(input_path)

        if not path.exists():
            raise InvalidInputError(f"Input path '{input_path}' does not exist.")

        if path.is_file() and path.suffix.lower() == '.zip':
            return 'ZIP'
        elif path.is_dir():
            return 'FOLDER'
        else:
            raise InvalidInputError(
                f"Input path '{input_path}' is neither a ZIP file nor a folder."
            )
