from fastapi import FastAPI
from celery import Celery
from pydantic import BaseModel, HttpUrl, Field, AliasChoices
import os

# --- Pydantic Models ---
class SaveRequest(BaseModel):
    url: HttpUrl
    id: str = Field(
        description="Identifier specific to the URL",
        validation_alias=AliasChoices("id", "user_id"),
        serialization_alias="id",
    )

class TaskAccepted(BaseModel):
    task_id: str

# --- Celery Configuration ---
celery_broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
celery_backend_url = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')

# This Celery instance is configured as a producer to send tasks.
# The actual task implementation will be in the task_manager service.
celery_app = Celery(
    'archiver_producer',
    broker=celery_broker_url,
    backend=celery_backend_url
)

# --- FastAPI Application ---
app = FastAPI(title="Archiver Service")

@app.post("/archive", response_model=TaskAccepted, status_code=202)
async def create_archive_task(request: SaveRequest):
    """
    Receives a request to archive a URL, places it on the task queue,
    and returns a task ID for status polling.
    """
    # The task name 'task_manager.tasks.start_archive' must match the task
    # defined in the Celery worker (task_manager service).
    task = celery_app.send_task(
        'task_manager.tasks.start_archive',
        args=[str(request.url), request.id]
    )
    return {"task_id": task.id}

@app.get("/hello")
def read_root():
    return {"Hello": "Archiver"}

@app.post("/hello")
async def post_root():
    return {"Hello": "Archiver"}
