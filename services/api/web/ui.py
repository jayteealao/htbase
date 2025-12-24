from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

from core.config import get_settings


router = APIRouter()


@router.get("/ui", response_class=HTMLResponse)
def ui_page():
    settings = get_settings()
    ht_url = f"http://{settings.ht_listen}"
    template_path = Path(__file__).with_name("templates") / "ui.html"
    html = template_path.read_text(encoding="utf-8").replace("HTPREVIEW_URL", ht_url)
    return HTMLResponse(content=html)
