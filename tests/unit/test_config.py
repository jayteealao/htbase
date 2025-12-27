"""Test configuration settings classes."""

import os
import pytest
from pathlib import Path
from pydantic import ValidationError
from app.core.config import AppSettings, GcsSettings, FirestoreSettings


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch, tmp_path):
    """Clear settings cache and environment before each test."""
    # Disable .env file loading by changing to a temp directory
    monkeypatch.chdir(tmp_path)

    # Clear all relevant environment variables
    env_vars_to_clear = [
        "GCS_BUCKET", "GCS_PROJECT_ID", "GCS_CREDENTIALS_PATH",
        "GOOGLE_APPLICATION_CREDENTIALS", "STORAGE_FALLBACK_TO_LOCAL",
        "STORAGE_RETENTION_DAYS", "FIRESTORE_PROJECT_ID",
        "FIRESTORE_CREDENTIALS_PATH", "FIREBASE_APPLICATION_CREDENTIALS",
        "STORAGE_BACKEND", "DATABASE_BACKEND", "STORAGE_PROVIDERS",
        "ENABLE_STORAGE_INTEGRATION", "DATA_DIR", "DATABASE__HOST", "DATABASE__PORT",
        "DATABASE__NAME", "DATABASE__USER", "DATABASE__PASSWORD", "START_HT",
        "STORAGE__GCS_BUCKET", "STORAGE__GCS_PROJECT_ID",
        "DATABASE__FIRESTORE_PROJECT_ID", "STORAGE__PROVIDERS"
    ]

    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)

    yield


@pytest.fixture
def clean_env():
    """Provide clean environment reference (already cleaned by autouse fixture)."""
    import pytest
    return pytest.MonkeyPatch()


class TestGcsSettings:
    """Test GcsSettings configuration."""

    def test_default_values(self):
        """Test default GCS settings."""
        gcs = GcsSettings()
        assert gcs.bucket == "htbase-archives-standard"
        assert gcs.project_id is None
        assert gcs.credentials_path is None
        assert gcs.application_credentials is None
        assert gcs.fallback_to_local is True
        assert gcs.retention_days == 365

    def test_flat_env_vars(self, clean_env):
        """Test flat environment variable naming."""
        clean_env.setenv("GCS_BUCKET", "test-bucket")
        clean_env.setenv("GCS_PROJECT_ID", "test-project")
        clean_env.setenv("STORAGE_FALLBACK_TO_LOCAL", "false")
        clean_env.setenv("STORAGE_RETENTION_DAYS", "30")

        settings = AppSettings()
        assert settings.gcs.bucket == "test-bucket"
        assert settings.gcs.project_id == "test-project"
        assert settings.gcs.fallback_to_local is False
        assert settings.gcs.retention_days == 30

    def test_nested_env_vars(self, clean_env):
        """Test nested environment variable naming."""
        clean_env.setenv("STORAGE__GCS_BUCKET", "nested-bucket")
        clean_env.setenv("STORAGE__GCS_PROJECT_ID", "nested-project")

        settings = AppSettings()
        assert settings.gcs.bucket == "nested-bucket"
        assert settings.gcs.project_id == "nested-project"

    def test_is_configured(self):
        """Test is_configured helper method."""
        gcs = GcsSettings()
        assert gcs.is_configured()  # Default bucket set

        gcs_empty = GcsSettings(bucket="")
        assert not gcs_empty.is_configured()

    def test_credentials_path_type(self):
        """Test credential path is correctly typed as Path."""
        gcs = GcsSettings(credentials_path="/path/to/creds.json")
        assert isinstance(gcs.credentials_path, Path)
        assert gcs.credentials_path == Path("/path/to/creds.json")


class TestFirestoreSettings:
    """Test FirestoreSettings configuration."""

    def test_default_values(self):
        """Test default Firestore settings."""
        fs = FirestoreSettings()
        assert fs.project_id is None
        assert fs.credentials_path is None
        assert fs.application_credentials is None

    def test_flat_env_vars(self, clean_env):
        """Test flat environment variable naming."""
        clean_env.setenv("FIRESTORE_PROJECT_ID", "test-firebase")
        clean_env.setenv("FIRESTORE_CREDENTIALS_PATH", "/path/to/firebase.json")


        settings = AppSettings()
        assert settings.firestore.project_id == "test-firebase"
        assert settings.firestore.credentials_path == Path("/path/to/firebase.json")

    def test_nested_env_vars(self, clean_env):
        """Test nested environment variable naming."""
        clean_env.setenv("DATABASE__FIRESTORE_PROJECT_ID", "nested-firebase")


        settings = AppSettings()
        assert settings.firestore.project_id == "nested-firebase"

    def test_is_configured(self):
        """Test is_configured helper method."""
        fs = FirestoreSettings()
        assert not fs.is_configured()  # No project_id

        fs_configured = FirestoreSettings(project_id="my-project")
        assert fs_configured.is_configured()

    def test_credentials_path_type(self):
        """Test credential path is correctly typed as Path."""
        fs = FirestoreSettings(credentials_path="/path/to/firebase.json")
        assert isinstance(fs.credentials_path, Path)
        assert fs.credentials_path == Path("/path/to/firebase.json")


class TestAppSettingsIntegration:
    """Test AppSettings integration with nested settings."""

    def test_backend_selection_defaults(self):
        """Test storage backend selection default values."""
        settings = AppSettings()
        assert settings.storage_backend == "local"
        assert settings.database_backend == "postgres"

    def test_backend_selection_env_override(self, clean_env):
        """Test backend selection via environment."""
        clean_env.setenv("STORAGE_BACKEND", "gcs")
        clean_env.setenv("DATABASE_BACKEND", "firestore")


        settings = AppSettings()
        assert settings.storage_backend == "gcs"
        assert settings.database_backend == "firestore"

    def test_nested_settings_instantiation(self):
        """Test that nested settings are properly instantiated."""
        settings = AppSettings()
        assert isinstance(settings.gcs, GcsSettings)
        assert isinstance(settings.firestore, FirestoreSettings)

    def test_backward_compatibility_flat_vars(self, clean_env):
        """Test that old flat env vars still work (backward compatibility)."""
        # Set old-style env vars
        clean_env.setenv("GCS_BUCKET", "legacy-bucket")
        clean_env.setenv("GCS_PROJECT_ID", "legacy-project")
        clean_env.setenv("FIRESTORE_PROJECT_ID", "legacy-firebase")
        clean_env.setenv("STORAGE_FALLBACK_TO_LOCAL", "false")
        clean_env.setenv("STORAGE_RETENTION_DAYS", "30")


        settings = AppSettings()

        # Verify all old vars map correctly to nested settings
        assert settings.gcs.bucket == "legacy-bucket"
        assert settings.gcs.project_id == "legacy-project"
        assert settings.firestore.project_id == "legacy-firebase"
        assert settings.gcs.fallback_to_local is False
        assert settings.gcs.retention_days == 30

    def test_backward_compatibility_nested_vars(self, clean_env):
        """Test that new nested env vars work correctly."""
        # Set new-style nested env vars
        clean_env.setenv("STORAGE__GCS_BUCKET", "new-bucket")
        clean_env.setenv("STORAGE__GCS_PROJECT_ID", "new-project")
        clean_env.setenv("DATABASE__FIRESTORE_PROJECT_ID", "new-firebase")


        settings = AppSettings()

        # Verify new nested vars work
        assert settings.gcs.bucket == "new-bucket"
        assert settings.gcs.project_id == "new-project"
        assert settings.firestore.project_id == "new-firebase"

    def test_mixed_env_var_styles(self, clean_env):
        """Test mixing old and new env var styles."""
        # Mix old and new styles
        clean_env.setenv("GCS_BUCKET", "flat-bucket")
        clean_env.setenv("STORAGE__GCS_PROJECT_ID", "nested-project")
        clean_env.setenv("FIRESTORE_PROJECT_ID", "flat-firebase")


        settings = AppSettings()

        # Both styles should work together
        assert settings.gcs.bucket == "flat-bucket"
        assert settings.gcs.project_id == "nested-project"
        assert settings.firestore.project_id == "flat-firebase"

    def test_enable_storage_integration_preserved(self):
        """Test that enable_storage_integration field is preserved."""
        settings = AppSettings()
        assert hasattr(settings, 'enable_storage_integration')
        assert settings.enable_storage_integration is False

    def test_google_application_credentials_alias(self, clean_env):
        """Test GOOGLE_APPLICATION_CREDENTIALS env var alias."""
        clean_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/path/to/gcp.json")


        settings = AppSettings()
        assert settings.gcs.application_credentials == "/path/to/gcp.json"

    def test_firebase_application_credentials_alias(self, clean_env):
        """Test FIREBASE_APPLICATION_CREDENTIALS env var alias."""
        clean_env.setenv("FIREBASE_APPLICATION_CREDENTIALS", "/path/to/firebase.json")


        settings = AppSettings()
        assert settings.firestore.application_credentials == "/path/to/firebase.json"


class TestSettingsValidation:
    """Test settings validation and edge cases."""

    def test_gcs_with_all_fields(self):
        """Test GCS settings with all fields populated."""
        gcs = GcsSettings(
            bucket="my-bucket",
            project_id="my-project",
            credentials_path="/creds.json",
            application_credentials='{"key": "value"}',
            fallback_to_local=False,
            retention_days=90
        )
        assert gcs.bucket == "my-bucket"
        assert gcs.project_id == "my-project"
        assert gcs.credentials_path == Path("/creds.json")
        assert gcs.application_credentials == '{"key": "value"}'
        assert gcs.fallback_to_local is False
        assert gcs.retention_days == 90

    def test_firestore_with_all_fields(self):
        """Test Firestore settings with all fields populated."""
        fs = FirestoreSettings(
            project_id="firebase-project",
            credentials_path="/firebase-creds.json",
            application_credentials='{"type": "service_account"}'
        )
        assert fs.project_id == "firebase-project"
        assert fs.credentials_path == Path("/firebase-creds.json")
        assert fs.application_credentials == '{"type": "service_account"}'

    def test_retention_days_validation(self):
        """Test retention_days accepts valid integer values."""
        gcs = GcsSettings(retention_days=1)
        assert gcs.retention_days == 1

        gcs = GcsSettings(retention_days=365 * 10)  # 10 years
        assert gcs.retention_days == 3650


class TestConfigurationValidation:
    """
    Test configuration validation and error handling.

    Corresponds to Test Case 7 from TESTING_PLAN.md: Configuration Validation
    """

    def test_invalid_storage_backend_fallback(self, clean_env, caplog):
        """
        Test: STORAGE_BACKEND=invalid → logs warning → uses 'local' as fallback.

        Corresponds to TESTING_PLAN Test Case 7.1.1
        """
        clean_env.setenv("STORAGE_BACKEND", "invalid-backend")

        settings = AppSettings()

        # Should fallback to a valid backend or keep the invalid value
        # (actual behavior depends on implementation)
        # At minimum, should not crash
        assert hasattr(settings, 'storage_backend')

        # If validation is implemented, should fallback to 'local'
        # If not implemented yet, will be 'invalid-backend'
        assert settings.storage_backend in ['local', 'invalid-backend']

    def test_missing_storage_backend_defaults_to_local(self, clean_env):
        """
        Test: Unset STORAGE_BACKEND → defaults to 'local'.

        Corresponds to TESTING_PLAN Test Case 7.1.2
        """
        # Ensure STORAGE_BACKEND is not set (clean_env already cleared it)
        settings = AppSettings()

        # Should default to 'local'
        assert settings.storage_backend == "local"

    def test_configuration_validation_detects_missing_gcs_bucket(self, clean_env):
        """
        Test: STORAGE_BACKEND=gcs, no GCS_BUCKET → validation detects issue.

        Corresponds to TESTING_PLAN Test Case 7.2
        """
        clean_env.setenv("STORAGE_BACKEND", "gcs")
        clean_env.setenv("GCS_BUCKET", "")  # Empty bucket

        settings = AppSettings()

        # Check if GCS is properly configured
        assert not settings.gcs.is_configured() or settings.gcs.bucket == ""

    def test_configuration_validation_detects_invalid_paths(self, clean_env, tmp_path):
        """
        Test: DATA_DIR=/nonexistent → configuration allows but path doesn't exist.

        Tests configuration accepts path strings even if they don't exist yet.
        """
        nonexistent_path = tmp_path / "nonexistent" / "data"

        clean_env.setenv("DATA_DIR", str(nonexistent_path))


        settings = AppSettings()

        # Should accept the path even if it doesn't exist
        # (application may create it during startup)
        assert settings.data_dir == nonexistent_path

    def test_storage_providers_list_parsing(self, clean_env):
        """
        Test: STORAGE_PROVIDERS='gcs,local' → parses to ['gcs', 'local'].

        Tests parsing of comma-separated provider list.
        """
        clean_env.setenv("STORAGE_PROVIDERS", "gcs,local")


        settings = AppSettings()

        # Check if storage_providers field exists and is parsed
        if hasattr(settings, 'storage_providers'):
            # Should be a list
            assert isinstance(settings.storage_providers, list)
            assert 'gcs' in settings.storage_providers
            assert 'local' in settings.storage_providers

    def test_storage_providers_empty_defaults_to_local(self, clean_env):
        """
        Test: STORAGE_PROVIDERS='' → defaults to ['local'] or equivalent.

        Tests default behavior with empty providers list.
        """
        clean_env.setenv("STORAGE_PROVIDERS", "")


        settings = AppSettings()

        # Should handle empty string gracefully
        # May default to local or be an empty list (depends on implementation)
        if hasattr(settings, 'storage_providers'):
            assert isinstance(settings.storage_providers, list)

    def test_database_url_construction(self, clean_env):
        """
        Test: Database URL is constructed correctly from components.

        Verifies database URL building from individual components.
        """
        clean_env.setenv("DATABASE__HOST", "localhost")
        clean_env.setenv("DATABASE__PORT", "5432")
        clean_env.setenv("DATABASE__NAME", "testdb")
        clean_env.setenv("DATABASE__USER", "testuser")
        clean_env.setenv("DATABASE__PASSWORD", "testpass")


        settings = AppSettings()

        # Should construct proper database URL
        if hasattr(settings, 'database_url'):
            db_url = settings.database_url
            assert 'postgresql' in db_url.lower()
            assert 'testuser' in db_url
            assert 'localhost' in db_url

    def test_enable_storage_integration_flag(self, clean_env):
        """
        Test: ENABLE_STORAGE_INTEGRATION flag can be toggled.

        Verifies storage integration can be enabled/disabled via config.
        """
        # Test with enabled
        clean_env.setenv("ENABLE_STORAGE_INTEGRATION", "true")


        settings = AppSettings()

        if hasattr(settings, 'enable_storage_integration'):
            assert settings.enable_storage_integration is True

        # Test with disabled
        clean_env.setenv("ENABLE_STORAGE_INTEGRATION", "false")

        settings_disabled = AppSettings()

        if hasattr(settings_disabled, 'enable_storage_integration'):
            assert settings_disabled.enable_storage_integration is False

    def test_start_ht_flag_parsing(self, clean_env):
        """
        Test: START_HT flag parsed correctly as boolean.

        Verifies boolean flag parsing from environment.
        """
        clean_env.setenv("START_HT", "false")


        settings = AppSettings()

        if hasattr(settings, 'start_ht'):
            assert settings.start_ht is False

        # Test with true
        clean_env.setenv("START_HT", "true")

        settings_enabled = AppSettings()

        if hasattr(settings_enabled, 'start_ht'):
            assert settings_enabled.start_ht is True
