from datetime import datetime

class DateTimeUtils:
    """
    Utility functions for date and time operations.
    """

    @staticmethod
    def parse_timestamp(timestamp: str) -> datetime:
        """
        Parses a timestamp string into a datetime object.
        Supports both 12-hour and 24-hour formats.
        """
        try:
            return datetime.strptime(timestamp, '%m/%d/%Y, %I:%M %p')  # 12-hour format
        except ValueError:
            return datetime.strptime(timestamp, '%m/%d/%Y, %H:%M')  # 24-hour format

    @staticmethod
    def format_timestamp(dt: datetime) -> str:
        """
        Formats a datetime object into a string.
        """
        return dt.strftime('%Y-%m-%d %H:%M:%S')
