from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


@router.post("/ht/send", response_model=Dict[str, object])
def ht_send(
    request: Request,
    payload: str,
    wait_marker: str | None = None,
    timeout: float = 15.0,
):
    ht = getattr(request.app.state, "ht_runner", None)
    if ht is None:
        raise HTTPException(status_code=500, detail="ht runner not initialized")
    # Serialize access to ht via its internal lock
    from contextlib import ExitStack

    with ht.lock if hasattr(ht, "lock") else ExitStack():
        ht.send_input(payload)
        rc = None
        if wait_marker:
            rc = ht.wait_for_done_marker(wait_marker, timeout=timeout)
    return {"ok": True, "exit_code": rc}
