#!/usr/bin/env python3
"""
Cleanup script for test data in GCS and Firestore.

This script removes test artifacts created during integration testing.
It's designed to clean up test data that may have been left behind during
testing with real cloud services.

Usage:
    # Clean up all test data
    python tests/cleanup_test_data.py --all

    # Clean up GCS test data only
    python tests/cleanup_test_data.py --gcs

    # Clean up Firestore test data only
    python tests/cleanup_test_data.py --firestore

    # Dry run (show what would be deleted)
    python tests/cleanup_test_data.py --all --dry-run

Environment Variables:
    TEST_GCS_BUCKET: GCS bucket for testing
    TEST_GCS_PROJECT_ID: GCP project ID
    GOOGLE_APPLICATION_CREDENTIALS: Path to GCS credentials
    TEST_FIRESTORE_PROJECT: Firestore project for testing
    FIREBASE_APPLICATION_CREDENTIALS: Path to Firestore credentials
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def cleanup_gcs_test_data(dry_run=False, older_than_days=1):
    """
    Clean up test data from GCS.

    Args:
        dry_run: If True, only show what would be deleted
        older_than_days: Only delete files older than this many days
    """
    try:
        from google.cloud import storage
    except ImportError:
        print("❌ google-cloud-storage not installed")
        return False

    bucket_name = os.getenv("TEST_GCS_BUCKET")
    if not bucket_name:
        print("⚠️  TEST_GCS_BUCKET not set, skipping GCS cleanup")
        return True

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)

        # List all blobs with test prefix
        test_prefix = "test/"
        blobs = list(bucket.list_blobs(prefix=test_prefix))

        if not blobs:
            print("✅ No GCS test data found")
            return True

        # Filter by age
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        old_blobs = [
            blob for blob in blobs
            if blob.time_created.replace(tzinfo=None) < cutoff_date
        ]

        print(f"📊 GCS Cleanup Summary:")
        print(f"   Total test files: {len(blobs)}")
        print(f"   Files older than {older_than_days} days: {len(old_blobs)}")

        if not old_blobs:
            print("✅ No old test data to clean up")
            return True

        if dry_run:
            print("\n🔍 Dry run - would delete:")
            for blob in old_blobs[:10]:  # Show first 10
                print(f"   - {blob.name}")
            if len(old_blobs) > 10:
                print(f"   ... and {len(old_blobs) - 10} more")
            return True

        # Delete old blobs
        deleted_count = 0
        for blob in old_blobs:
            try:
                blob.delete()
                deleted_count += 1
            except Exception as e:
                print(f"⚠️  Failed to delete {blob.name}: {e}")

        print(f"✅ Deleted {deleted_count} GCS test files")
        return True

    except Exception as e:
        print(f"❌ GCS cleanup failed: {e}")
        return False


def cleanup_firestore_test_data(dry_run=False, older_than_days=1):
    """
    Clean up test data from Firestore.

    Args:
        dry_run: If True, only show what would be deleted
        older_than_days: Only delete documents older than this many days
    """
    try:
        from google.cloud import firestore
    except ImportError:
        print("❌ google-cloud-firestore not installed")
        return False

    project_id = os.getenv("TEST_FIRESTORE_PROJECT")
    if not project_id:
        print("⚠️  TEST_FIRESTORE_PROJECT not set, skipping Firestore cleanup")
        return True

    try:
        db = firestore.Client(project=project_id)

        # Query test articles (those with item_id starting with "test_" or "real_test_")
        test_prefixes = ["test_", "real_test_", "perf_", "batch_", "concurrent_"]

        total_docs = 0
        old_docs = []

        for prefix in test_prefixes:
            # Query articles collection
            articles_ref = db.collection("articles")

            # Note: This is a simple implementation
            # A more sophisticated version would use proper indexing
            docs = articles_ref.stream()

            for doc in docs:
                data = doc.to_dict()
                item_id = data.get("item_id", "")

                if not item_id.startswith(prefix):
                    continue

                total_docs += 1

                # Check age
                created_at = data.get("created_at")
                if created_at:
                    # Convert Firestore timestamp to datetime
                    if hasattr(created_at, 'timestamp'):
                        created_datetime = datetime.fromtimestamp(created_at.timestamp())
                    else:
                        created_datetime = created_at

                    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

                    if created_datetime < cutoff_date:
                        old_docs.append(doc.id)

        print(f"📊 Firestore Cleanup Summary:")
        print(f"   Total test documents: {total_docs}")
        print(f"   Documents older than {older_than_days} days: {len(old_docs)}")

        if not old_docs:
            print("✅ No old test data to clean up")
            return True

        if dry_run:
            print("\n🔍 Dry run - would delete:")
            for doc_id in old_docs[:10]:  # Show first 10
                print(f"   - {doc_id}")
            if len(old_docs) > 10:
                print(f"   ... and {len(old_docs) - 10} more")
            return True

        # Delete old documents
        deleted_count = 0
        articles_ref = db.collection("articles")

        for doc_id in old_docs:
            try:
                articles_ref.document(doc_id).delete()
                deleted_count += 1
            except Exception as e:
                print(f"⚠️  Failed to delete {doc_id}: {e}")

        print(f"✅ Deleted {deleted_count} Firestore test documents")
        return True

    except Exception as e:
        print(f"❌ Firestore cleanup failed: {e}")
        return False


def main():
    """Main cleanup function."""
    parser = argparse.ArgumentParser(description="Clean up HTBase test data")

    parser.add_argument(
        "--all",
        action="store_true",
        help="Clean up all test data (GCS + Firestore)"
    )
    parser.add_argument(
        "--gcs",
        action="store_true",
        help="Clean up GCS test data only"
    )
    parser.add_argument(
        "--firestore",
        action="store_true",
        help="Clean up Firestore test data only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    parser.add_argument(
        "--older-than",
        type=int,
        default=1,
        help="Only delete data older than this many days (default: 1)"
    )

    args = parser.parse_args()

    # Default to --all if no specific option provided
    if not (args.all or args.gcs or args.firestore):
        args.all = True

    print("🧹 HTBase Test Data Cleanup")
    print("=" * 60)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No data will be deleted")
        print("=" * 60)

    success = True

    # Clean up GCS
    if args.all or args.gcs:
        print("\n📦 GCS Cleanup")
        print("-" * 60)
        success = cleanup_gcs_test_data(
            dry_run=args.dry_run,
            older_than_days=args.older_than
        ) and success

    # Clean up Firestore
    if args.all or args.firestore:
        print("\n🔥 Firestore Cleanup")
        print("-" * 60)
        success = cleanup_firestore_test_data(
            dry_run=args.dry_run,
            older_than_days=args.older_than
        ) and success

    print("\n" + "=" * 60)
    if success:
        print("✅ Cleanup completed successfully")
        return 0
    else:
        print("❌ Cleanup completed with errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
