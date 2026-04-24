from celery import Celery

from app.core.config import get_settings

settings = get_settings()

broker_url = settings.redis_url
backend_url = settings.redis_url
if settings.celery_task_always_eager:
    broker_url = "memory://"
    backend_url = "cache+memory://"

celery_app = Celery(
    "lexquest",
    broker=broker_url,
    backend=backend_url,
)

celery_app.conf.update(
    task_routes={
        "app.workers.generation.generate_images": {"queue": "generation"},
        "app.workers.generation.process_generation_job": {"queue": "generation"},
        "app.workers.generation.pipeline_check": {"queue": "generation"},
    },
    task_default_queue="generation",
    timezone="UTC",
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=settings.celery_task_always_eager,
    broker_connection_retry_on_startup=True,
)

# Import tasks to register them with Celery
from app.workers import generation  # noqa: F401, E402
