from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from core.config import AppSettings, get_settings
from db.repository import get_task_rows
from models import TaskStatusResponse, TaskItemStatus


router = APIRouter()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str, settings: AppSettings = Depends(get_settings)):
    rows = get_task_rows(settings.resolved_db_path, task_id)
    if not rows:
        raise HTTPException(status_code=404, detail="task not found")
    items: List[TaskItemStatus] = []
    for r in rows:
        # prefer explicit status if present, fallback to success int
        status_val = r.get("status")
        if not status_val:
            status_val = "success" if int(r.get("success", 0) or 0) == 1 else "failed"
        item_id = r.get("item_id") or r.get("user_id") or ""
        items.append(
            TaskItemStatus(
                url=r.get("url"),
                id=item_id,
                name=r.get("name"),
                status=status_val,
                exit_code=r.get("exit_code"),
                saved_path=r.get("saved_path"),
                db_rowid=r.get("rowid"),
            )
        )
    # Aggregate overall status
    overall = "pending" if any(i.status == "pending" for i in items) else (
        "failed" if any(i.status == "failed" for i in items) else "success"
    )
    return TaskStatusResponse(task_id=task_id, status=overall, items=items)
