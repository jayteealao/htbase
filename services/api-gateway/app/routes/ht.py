"""
HyperTerm API routes.

Provides endpoints for HyperTerm runner integration.
"""

from __future__ import annotations

from contextlib import ExitStack
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.rate_limit import rate_limit_admin

router = APIRouter()


@router.post("/send", response_model=Dict[str, object], dependencies=[Depends(rate_limit_admin)])
async def ht_send(
    request: Request,
    payload: str,
    wait_marker: str | None = None,
    timeout: float = 15.0,
):
    """
    Send command to HyperTerm runner.

    Requires ht_runner to be initialized in app state.
    """
    ht = getattr(request.app.state, "ht_runner", None)
    if ht is None:
        raise HTTPException(status_code=500, detail="ht runner not initialized")

    # Serialize access to ht via its internal lock
    with ht.lock if hasattr(ht, "lock") else ExitStack():
        ht.send_input(payload)
        rc = None
        if wait_marker:
            rc = ht.wait_for_done_marker(wait_marker, timeout=timeout)

    return {"ok": True, "exit_code": rc}
