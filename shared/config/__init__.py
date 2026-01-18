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

# Legacy compatibility - for gradual migration keep old SharedSettings available
# Import from parent shared/config.py (the monolithic config file)
try:
    # Import relative to shared package
    import sys
    import os
    _shared_dir = os.path.dirname(os.path.dirname(__file__))
    _config_path = os.path.join(_shared_dir, 'config.py')

    if os.path.exists(_config_path):
        # Import from the old config.py file
        import importlib.util
        spec = importlib.util.spec_from_file_location("_old_config", _config_path)
        if spec and spec.loader:
            _old_config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_old_config)
            SharedSettings = _old_config.SharedSettings
            get_settings = _old_config.get_settings
        else:
            raise ImportError("Could not load config.py")
    else:
        raise ImportError("config.py not found")
except ImportError:
    # Fallback: create minimal stubs (shouldn't happen in practice)
    from .base import BaseSettings, configure_logging as _configure_logging
    SharedSettings = BaseSettings  # type: ignore

    from functools import lru_cache
    @lru_cache
    def get_settings():
        return BaseSettings()

    configure_logging = _configure_logging

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
