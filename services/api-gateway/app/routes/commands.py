"""
Commands API routes.

Provides endpoints for viewing command execution history and replaying commands.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared.db import get_session, CommandExecution, CommandOutputLine

logger = logging.getLogger(__name__)

router = APIRouter()


def get_db():
    """Database session dependency."""
    with get_session() as session:
        yield session


# Response Models


class CommandOutputLineResponse(BaseModel):
    """Response model for a single output line."""

    id: int
    timestamp: str
    stream: str
    line: str
    line_number: Optional[int] = None


class CommandExecutionResponse(BaseModel):
    """Response model for a command execution."""

    id: int
    command: str
    start_time: str
    end_time: Optional[str] = None
    exit_code: Optional[int] = None
    timed_out: bool
    timeout: float
    duration_seconds: Optional[float] = None
    archived_url_id: Optional[int] = None
    archiver: Optional[str] = None


class CommandExecutionDetailResponse(CommandExecutionResponse):
    """Response model for a command execution with full output."""

    output_lines: List[CommandOutputLineResponse]


@router.get("/executions", response_model=List[CommandExecutionResponse])
async def list_executions(
    archived_url_id: Optional[int] = Query(
        None, description="Filter by archived URL ID"
    ),
    archiver: Optional[str] = Query(None, description="Filter by archiver name"),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of executions to return"
    ),
    db: Session = Depends(get_db),
):
    """
    List command executions with optional filtering.

    Returns most recent executions first.
    """
    query = db.query(CommandExecution).order_by(CommandExecution.start_time.desc())

    if archived_url_id is not None:
        query = query.filter(CommandExecution.archived_url_id == archived_url_id)

    if archiver:
        query = query.filter(CommandExecution.archiver == archiver)

    query = query.limit(limit)
    executions = query.all()

    results = []
    for exe in executions:
        duration = None
        if exe.start_time and exe.end_time:
            duration = (exe.end_time - exe.start_time).total_seconds()

        results.append(
            CommandExecutionResponse(
                id=exe.id,
                command=exe.command,
                start_time=exe.start_time.isoformat() if exe.start_time else "",
                end_time=exe.end_time.isoformat() if exe.end_time else None,
                exit_code=exe.exit_code,
                timed_out=exe.timed_out or False,
                timeout=exe.timeout or 0.0,
                duration_seconds=duration,
                archived_url_id=exe.archived_url_id,
                archiver=exe.archiver,
            )
        )

    return results


@router.get("/executions/{execution_id}", response_model=CommandExecutionDetailResponse)
async def get_execution_detail(
    execution_id: int,
    db: Session = Depends(get_db),
):
    """
    Get detailed information about a specific command execution including all output.

    This endpoint allows you to "replay" a past command execution to see exactly
    what happened, including all stdin/stdout/stderr with timestamps.
    """
    execution = (
        db.query(CommandExecution).filter(CommandExecution.id == execution_id).first()
    )

    if not execution:
        raise HTTPException(
            status_code=404, detail=f"Command execution {execution_id} not found"
        )

    # Get output lines
    output_lines = (
        db.query(CommandOutputLine)
        .filter(CommandOutputLine.command_execution_id == execution_id)
        .order_by(CommandOutputLine.line_number)
        .all()
    )

    duration = None
    if execution.start_time and execution.end_time:
        duration = (execution.end_time - execution.start_time).total_seconds()

    return CommandExecutionDetailResponse(
        id=execution.id,
        command=execution.command,
        start_time=execution.start_time.isoformat() if execution.start_time else "",
        end_time=execution.end_time.isoformat() if execution.end_time else None,
        exit_code=execution.exit_code,
        timed_out=execution.timed_out or False,
        timeout=execution.timeout or 0.0,
        duration_seconds=duration,
        archived_url_id=execution.archived_url_id,
        archiver=execution.archiver,
        output_lines=[
            CommandOutputLineResponse(
                id=line.id,
                timestamp=line.timestamp.isoformat() if line.timestamp else "",
                stream=line.stream or "",
                line=line.line or "",
                line_number=line.line_number,
            )
            for line in output_lines
        ],
    )


@router.get("/executions/{execution_id}/replay")
async def replay_execution(
    execution_id: int,
    db: Session = Depends(get_db),
):
    """
    Replay a command execution log.

    This reconstructs the full execution from database logs without re-running the command.
    Useful for debugging and reviewing what happened during an archiving run.
    """
    # Get the detailed execution
    return await get_execution_detail(execution_id, db)
