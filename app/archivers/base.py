from __future__ import annotations

import abc
from typing import Optional

from config import AppSettings
from models import ArchiveResult


class BaseArchiver(abc.ABC):
    name: str = "base"

    def __init__(self, settings: AppSettings):
        self.settings = settings

    @abc.abstractmethod
    def archive(self, *, url: str, item_id: str, out_name: Optional[str]) -> ArchiveResult:  # noqa: D401
        """Archive the given URL keyed by item_id; returns result metadata."""
        raise NotImplementedError
