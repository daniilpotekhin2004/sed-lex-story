import logging
import logging.config


def configure_logging(log_level: str = "INFO") -> None:
    """Configure basic structured logging for the app and workers."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
                }
            },
            "handlers": {
                "default": {
                    "level": log_level,
                    "formatter": "standard",
                    "class": "logging.StreamHandler",
                }
            },
            "loggers": {
                "": {"handlers": ["default"], "level": log_level},
                "uvicorn": {"handlers": ["default"], "level": log_level},
                "celery": {"handlers": ["default"], "level": log_level},
            },
        }
    )
