"""API endpoints for viewing command execution history and replaying commands."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from common.core.command_runner import CommandRunner
from common.db import CommandExecutionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commands", tags=["commands"])


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
def list_executions(
    archived_url_id: Optional[int] = Query(None, description="Filter by archived URL ID"),
    archiver: Optional[str] = Query(None, description="Filter by archiver name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of executions to return"),
):
    """
    List command executions with optional filtering.

    Returns most recent executions first.
    """
    cmd_repo = CommandExecutionRepository()
    executions = cmd_repo.list_executions(
        archived_url_id=archived_url_id,
        archiver=archiver,
        limit=limit,
    )

    results = []
    for exe in executions:
            duration = None
            if exe.start_time and exe.end_time:
                duration = (exe.end_time - exe.start_time).total_seconds()

            results.append(
                CommandExecutionResponse(
                    id=exe.id,
                    command=exe.command,
                    start_time=exe.start_time.isoformat(),
                    end_time=exe.end_time.isoformat() if exe.end_time else None,
                    exit_code=exe.exit_code,
                    timed_out=exe.timed_out or False,
                    timeout=exe.timeout,
                    duration_seconds=duration,
                    archived_url_id=exe.archived_url_id,
                    archiver=exe.archiver,
                )
            )

    return results


@router.get("/executions/{execution_id}", response_model=CommandExecutionDetailResponse)
def get_execution_detail(execution_id: int):
    """
    Get detailed information about a specific command execution including all output.

    This endpoint allows you to "replay" a past command execution to see exactly
    what happened, including all stdin/stdout/stderr with timestamps.
    """
    cmd_repo = CommandExecutionRepository()
    execution = cmd_repo.get_by_id(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Command execution {execution_id} not found")

    output_lines = cmd_repo.get_output_lines(execution_id)

    duration = None
    if execution.start_time and execution.end_time:
        duration = (execution.end_time - execution.start_time).total_seconds()

    return CommandExecutionDetailResponse(
        id=execution.id,
        command=execution.command,
        start_time=execution.start_time.isoformat(),
        end_time=execution.end_time.isoformat() if execution.end_time else None,
        exit_code=execution.exit_code,
        timed_out=execution.timed_out or False,
        timeout=execution.timeout,
        duration_seconds=duration,
        archived_url_id=execution.archived_url_id,
        archiver=execution.archiver,
        output_lines=[
            CommandOutputLineResponse(
                id=line.id,
                timestamp=line.timestamp.isoformat(),
                stream=line.stream,
                line=line.line,
                line_number=line.line_number,
            )
            for line in output_lines
        ],
    )


@router.get("/executions/{execution_id}/replay")
def replay_execution(execution_id: int):
    """
    Replay a command execution using CommandRunner.replay().

    This reconstructs the full execution from database logs without re-running the command.
    Useful for debugging and reviewing what happened during an archiving run.
    """
    # Note: This endpoint requires CommandRunner to be initialized
    # For now, we'll just redirect to the detail endpoint
    # In production, you'd inject CommandRunner from request.app.state
    from fastapi import Request

    # runner = request.app.state.command_runner
    # result = runner.replay(execution_id)

    # For now, just return the detailed view
    return get_execution_detail(execution_id)
