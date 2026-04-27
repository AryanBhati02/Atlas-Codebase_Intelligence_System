"""
Celery application — broker and result backend both use Redis.

Starting the worker
───────────────────
    cd backend
    celery -A workers.celery_app worker --loglevel=info --concurrency=2

worker_chdir
────────────
Python's sys.path always contains '' which resolves to os.getcwd() at the
moment an import statement is executed (not at interpreter startup).

When Celery is started from outside backend/ the CWD is wrong, so
`from config import ...` and `from core. import ...` fail with
ModuleNotFoundError.

worker_chdir tells Celery to os.chdir() to backend/ before it begins
accepting tasks.  Once CWD == backend/, the '' entry in sys.path causes
every bare `import config` and `from core.X import Y` to resolve correctly,
regardless of where the `celery` command was invoked from.

This is a Celery-native mechanism — no sys.path manipulation is needed.
"""

from pathlib import Path
from celery import Celery

# backend/ is the parent of workers/ (where this file lives).
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)

print("🔥 USING CELERY APP FROM:", __file__)
print("🔥 BACKEND DIR:", _BACKEND_DIR)

celery_app = Celery(
    "codebase_intel",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Track task state transitions (PENDING → STARTED → SUCCESS/FAILURE).
    task_track_started=True,
    # Acknowledge the task only after it completes so a worker crash re-queues it.
    task_acks_late=True,
    # Fetch one task at a time; prevents slow tasks starving the queue.
    worker_prefetch_multiplier=1,
    # Recover gracefully from transient Redis restarts.
    broker_connection_retry_on_startup=True,
    # ── PATH FIX ─────────────────────────────────────────────────────────────
    # Change the worker's CWD to backend/ before it starts loading tasks.
    # Python's '' sys.path entry then resolves to backend/, making all bare
    # imports (config, core.*, api.*, models.*, utils.*) work correctly from
    # any launch directory.
    worker_chdir=_BACKEND_DIR,
)
