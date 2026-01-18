"""Configuration module for HTBase services.

Provides service-specific configuration classes that extend BaseSettings.
Each service imports only the settings it needs.

Example:
    from shared.config import APIGatewaySettings
    settings = APIGatewaySettings()
"""

from .base import (
    BaseSettings,
    RedisSettings,
    FirestoreSettings,
    configure_logging,
)
from .api_gateway import APIGatewaySettings
from .archive_worker import ArchiveWorkerSettings, GCSSettings
from .summarization_worker import SummarizationWorkerSettings

# Legacy compatibility - import SharedSettings from old config.py
# This allows gradual migration from SharedSettings to service-specific settings
import sys
from pathlib import Path

# Add parent directory to path to import old config.py
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from config import SharedSettings, get_settings
except ImportError:
    # If old config.py doesn't exist, create stub for backward compatibility
    SharedSettings = None
    get_settings = None

__all__ = [
    # Base settings components
    "BaseSettings",
    "RedisSettings",
    "FirestoreSettings",
    "GCSSettings",
    # Service-specific settings
    "APIGatewaySettings",
    "ArchiveWorkerSettings",
    "SummarizationWorkerSettings",
    # Utilities
    "configure_logging",
    # Legacy compatibility (deprecated, use service-specific settings)
    "SharedSettings",
    "get_settings",
]
