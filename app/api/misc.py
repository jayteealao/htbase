from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Health check endpoint (Cloud Run default)."""
    return {"status": "ok"}


@router.get("/healthz")
def healthz():
    """Health check endpoint (Kubernetes style)."""
    return {"status": "ok"}

