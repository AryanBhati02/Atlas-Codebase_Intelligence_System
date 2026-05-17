import os
from pathlib import Path
from celery import Celery

_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)

print("🔥 USING CELERY APP FROM:", __file__)
print("🔥 BACKEND DIR:", _BACKEND_DIR)

# REDIS_URL is injected by Docker Compose (redis://redis:6379/0).
# Falls back to localhost so local `uvicorn` / `celery` runs still work.
_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "codebase_intel",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
                                                                         
    task_track_started=True,
                                                                                  
    task_acks_late=True,
                                                                       
    worker_prefetch_multiplier=1,
                                                       
    broker_connection_retry_on_startup=True,
                                                                               
    worker_chdir=_BACKEND_DIR,
)
