"""
Shared module for HTBase microservices.

Contains common code used across all services:
- celery_config: Celery application and task configuration
- status: Task status enums and tracking
- models: Pydantic models for API requests/responses
- db: Database models, schemas, and session management
- storage: File and database storage provider interfaces
- utils: Utility functions
"""

from shared.celery_config import celery_app
from shared.status import TaskStatus, TaskResult

__all__ = [
    "celery_app",
    "TaskStatus",
    "TaskResult",
]
