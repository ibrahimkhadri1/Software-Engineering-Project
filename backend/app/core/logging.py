import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

# Allowlist: any other `extra=` field is dropped so student content can't reach the logs.
SAFE_FIELDS = ("method", "path", "status", "latency_ms", "safe_error_code", "result_id", "count")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(),
        }
        entry.update({k: getattr(record, k) for k in SAFE_FIELDS if hasattr(record, k)})
        if record.exc_info:
            entry["exception"] = record.exc_info[0].__name__
        return json.dumps(entry)


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
