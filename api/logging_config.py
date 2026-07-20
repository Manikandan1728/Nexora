import logging
import sys
from pythonjsonlogger import jsonlogger
from asgi_correlation_id.context import correlation_id

class CorrelationIdJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['correlation_id'] = correlation_id.get() or "N/A"

def setup_logging(log_level: str = "INFO"):
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logHandler = logging.StreamHandler(sys.stdout)
    formatter = CorrelationIdJsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s'
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)

    # Prevent noisy third-party logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
