#!/usr/bin/env python3
"""
Verify GCS and Firestore connectivity for HTBase.
Run this script to test your configuration.
"""

import sys
import os
from pathlib import Path

# Fix Windows console encoding for special characters
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Load .env BEFORE importing config to ensure pydantic-settings picks it up
from dotenv import load_dotenv
env_file = Path(__file__).parent / ".env"
load_dotenv(env_file, override=True)

# Add app to path BEFORE importing to ensure proper initialization
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Now import and force reload of settings
from shared.config import get_settings
# Clear the LRU cache to force fresh load
get_settings.cache_clear()

# Debug: Check if env var is loaded
print(f"[DEBUG] FIRESTORE_PROJECT_ID from os.environ: {os.environ.get('FIRESTORE_PROJECT_ID')}")
print(f"[DEBUG] DATABASE_BACKEND from os.environ: {os.environ.get('DATABASE_BACKEND')}")
print()

from storage.gcs_file_storage import GCSFileStorage
from storage.firestore_storage import FirestoreStorage

def verify_firestore():
    """Test Firestore connection."""
    print("=" * 60)
    print("FIRESTORE VERIFICATION")
    print("=" * 60)

    # Read project ID directly from environment as pydantic nested models have issues
    project_id = os.environ.get('FIRESTORE_PROJECT_ID')
    google_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')

    if not project_id:
        print("[X] FIRESTORE_PROJECT_ID not configured")
        return False

    print(f"[OK] Project ID: {project_id}")
    if google_creds:
        print(f"[OK] Credentials: {google_creds}")
        if not Path(google_creds).exists():
            print(f"[!] Warning: Credentials file not found at {google_creds}")
            print("     You need to download the Firebase service account JSON")

    try:
        # Initialize Firestore client with environment project ID
        firestore_storage = FirestoreStorage(project_id=project_id)

        # Test basic operation - count articles
        count = firestore_storage.count_articles()
        print(f"[OK] Successfully connected to Firestore")
        print(f"     Article count: {count}")

        return True

    except Exception as e:
        print(f"[X] Firestore connection failed: {e}")
        return False


def verify_gcs():
    """Test GCS connection."""
    print("\n" + "=" * 60)
    print("GOOGLE CLOUD STORAGE VERIFICATION")
    print("=" * 60)

    settings = get_settings()

    if not settings.gcs.bucket:
        print("[X] GCS_BUCKET not configured")
        return False

    print(f"[OK] Bucket: {settings.gcs.bucket}")
    print(f"[OK] Project ID: {settings.gcs.project_id or '(using default credentials)'}")

    try:
        # Initialize GCS client
        gcs_storage = GCSFileStorage(
            bucket_name=settings.gcs.bucket,
            project_id=settings.gcs.project_id
        )

        # Test basic operation - list files
        files = gcs_storage.list_files(limit=5)
        print(f"[OK] Successfully connected to GCS")
        print(f"     Bucket exists and accessible")
        print(f"     Files found: {len(files)}")

        return True

    except Exception as e:
        print(f"[X] GCS connection failed: {e}")
        print("\nCommon issues:")
        print("  - Bucket doesn't exist")
        print("  - Invalid credentials")
        print("  - Wrong project ID")
        print("  - Missing IAM permissions (Storage Admin role)")
        return False


def main():
    """Run all verification checks."""
    print("\nHTBase Storage Provider Verification")
    print("=" * 60)

    # Check if .env exists
    env_path = Path(__file__).parent / ".env"
    print(f"[DEBUG] .env path: {env_path}")
    print(f"[DEBUG] .env exists: {env_path.exists()}")
    print()

    # Try creating settings directly
    from core.config import AppSettings
    settings = AppSettings(_env_file=env_path)

    print(f"[DEBUG] After direct init - Firestore project_id: {settings.firestore.project_id}")
    print()

    print(f"Storage Providers: {settings.storage_providers}")
    print(f"Database Backend: {settings.database_backend}")
    print()

    firestore_ok = verify_firestore()
    gcs_ok = verify_gcs()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Firestore: {'[OK] Connected' if firestore_ok else '[X] Failed'}")
    print(f"GCS:       {'[OK] Connected' if gcs_ok else '[X] Failed'}")
    print("=" * 60)

    if firestore_ok and gcs_ok:
        print("\n*** All systems operational! ***")
        return 0
    else:
        print("\n[!] Some connections failed. Check configuration above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
