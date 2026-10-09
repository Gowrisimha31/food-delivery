# logger.py
# Sets up logging for the whole app.
# Every log line goes to two places:
#   1. The terminal, in a format easy for humans to read
#   2. The file logs/app.log, in JSON format, easy for programs (and our AI) to read

import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

# Holds the ID of the request currently being handled,
# so every log line from one request shares the same ID.
request_id_var = ContextVar("request_id", default="-")

# Fields that Python adds to every log record. We skip these
# when collecting the extra details we attached ourselves.
_STANDARD_FIELDS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "food-app",
            "module": record.module,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        # Add any extra details, like order_id or total
        for key, value in vars(record).items():
            if key not in _STANDARD_FIELDS:
                entry[key] = value
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


class ReadableFormatter(logging.Formatter):
    def format(self, record):
        time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_FIELDS}
        extra_str = "  " + " ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""
        line = f"{time_str}  {record.levelname:<7} [{request_id_var.get()}] {record.getMessage()}{extra_str}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging():
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("food-app")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    terminal = logging.StreamHandler()
    terminal.setFormatter(ReadableFormatter())

    # Starts a new file once this one reaches 5 MB, keeping the last 3
    log_file = RotatingFileHandler("logs/app.log", maxBytes=5_000_000, backupCount=3)
    log_file.setFormatter(JSONFormatter())

    logger.addHandler(terminal)
    logger.addHandler(log_file)
    return logger


log = setup_logging()