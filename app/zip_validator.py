import zipfile
import os
from exceptions.exceptions import ZipValidationError


class ZipValidator:
    """
    Validates ZIP files for existence, integrity, and content.
    """

    @staticmethod
    def validate_zip(zip_path: str) -> None:
        """
        Verifies that the file exists, is a ZIP archive, and is not corrupted.
        Raises ZipValidationError for invalid ZIP files.
        """
        if not os.path.exists(zip_path):
            raise ZipValidationError(f"ZIP file '{zip_path}' does not exist.")

        if not zipfile.is_zipfile(zip_path):
            raise ZipValidationError(f"'{zip_path}' is not a valid ZIP file.")

        with zipfile.ZipFile(zip_path) as zip_file:
            if len(zip_file.namelist()) == 0:
                raise ZipValidationError(f"ZIP file '{zip_path}' is empty.")

            # testzip() returns the name of the first bad file, or None if all are OK
            bad_file = zip_file.testzip()
            if bad_file is not None:
                raise ZipValidationError(
                    f"ZIP file '{zip_path}' is corrupted (bad entry: {bad_file})."
                )
