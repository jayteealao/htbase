#!/usr/bin/env python3
"""
Verify that articles from missing_urls.csv have been successfully synced to:
1. PostgreSQL (archived_urls table)
2. Archive artifacts (archive_artifact table)
3. GCS bucket uploads

Generates a comprehensive verification report.
"""
import sys
import io
import csv
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from collections import defaultdict

# Set UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Database configuration
DB_CONFIG = {
    'host': 'postgres.archivist.lol',
    'port': 5432,
    'name': 'postgres',
    'user': 'archivist',
    'password': 'ed83e2f93719'
}

def create_db_connection():
    """Create database connection."""
    user = quote_plus(DB_CONFIG['user'])
    pwd = quote_plus(DB_CONFIG['password'])
    url = f"postgresql+psycopg://{user}:{pwd}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['name']}"
    return create_engine(url, pool_pre_ping=True)

def load_csv_articles(csv_path):
    """Load articles from CSV file."""
    articles = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            articles.append({
                'item_id': row['item_id'],
                'url': row['url']
            })
    return articles

def check_postgres_entries(engine, articles):
    """Check which articles exist in PostgreSQL."""
    print("\n" + "="*80)
    print("CHECKING POSTGRESQL ENTRIES")
    print("="*80)

    results = []

    with engine.connect() as conn:
        for article in articles:
            item_id = article['item_id']
            url = article['url']

            # Check archived_urls table
            result = conn.execute(text("""
                SELECT
                    id,
                    item_id,
                    url,
                    name,
                    created_at,
                    total_size_bytes
                FROM archived_urls
                WHERE item_id = :item_id OR url = :url
            """), {'item_id': item_id, 'url': url})

            row = result.fetchone()

            article_result = {
                'original_item_id': item_id,
                'url': url,
                'in_postgres': row is not None,
                'postgres_data': None
            }

            if row:
                article_result['postgres_data'] = {
                    'id': row.id,
                    'item_id': row.item_id,
                    'url': row.url,
                    'name': row.name,
                    'created_at': row.created_at,
                    'total_size_bytes': row.total_size_bytes
                }

            results.append(article_result)

    # Print summary
    in_postgres = sum(1 for r in results if r['in_postgres'])
    print(f"\n✓ Found in PostgreSQL: {in_postgres}/{len(articles)}")

    if in_postgres < len(articles):
        print(f"⚠️  Missing from PostgreSQL: {len(articles) - in_postgres}")
        print("\nMissing articles:")
        for r in results:
            if not r['in_postgres']:
                print(f"  - {r['original_item_id']}: {r['url'][:80]}...")

    return results

def check_archive_artifacts(engine, postgres_results):
    """Check archive artifacts for each article."""
    print("\n" + "="*80)
    print("CHECKING ARCHIVE ARTIFACTS")
    print("="*80)

    with engine.connect() as conn:
        for result in postgres_results:
            if not result['in_postgres']:
                result['artifacts'] = []
                continue

            archived_url_id = result['postgres_data']['id']

            # Get all artifacts for this article
            artifact_result = conn.execute(text("""
                SELECT
                    id,
                    archived_url_id,
                    archiver,
                    success,
                    exit_code,
                    saved_path,
                    status,
                    created_at,
                    updated_at,
                    size_bytes,
                    uploaded_to_storage,
                    storage_uploads,
                    all_uploads_succeeded,
                    local_file_deleted
                FROM archive_artifact
                WHERE archived_url_id = :archived_url_id
            """), {'archived_url_id': archived_url_id})

            artifacts = []
            for row in artifact_result:
                artifacts.append({
                    'id': row.id,
                    'archiver': row.archiver,
                    'success': row.success,
                    'exit_code': row.exit_code,
                    'saved_path': row.saved_path,
                    'status': row.status,
                    'created_at': row.created_at,
                    'updated_at': row.updated_at,
                    'size_bytes': row.size_bytes,
                    'uploaded_to_storage': row.uploaded_to_storage,
                    'storage_uploads': row.storage_uploads,
                    'all_uploads_succeeded': row.all_uploads_succeeded,
                    'local_file_deleted': row.local_file_deleted
                })

            result['artifacts'] = artifacts

    # Print summary
    total_with_artifacts = sum(1 for r in postgres_results if r['in_postgres'] and len(r.get('artifacts', [])) > 0)
    total_in_postgres = sum(1 for r in postgres_results if r['in_postgres'])

    print(f"\n✓ Articles with artifacts: {total_with_artifacts}/{total_in_postgres}")

    if total_with_artifacts < total_in_postgres:
        print(f"⚠️  Articles without artifacts: {total_in_postgres - total_with_artifacts}")

    return postgres_results

def check_gcs_uploads(results):
    """Check GCS upload status for artifacts."""
    print("\n" + "="*80)
    print("CHECKING GCS UPLOADS")
    print("="*80)

    total_artifacts = 0
    artifacts_with_gcs = 0
    artifacts_all_uploads_succeeded = 0

    for result in results:
        if not result['in_postgres']:
            continue

        for artifact in result.get('artifacts', []):
            total_artifacts += 1

            if artifact['uploaded_to_storage']:
                artifacts_with_gcs += 1

            if artifact['all_uploads_succeeded']:
                artifacts_all_uploads_succeeded += 1

    print(f"\nTotal artifacts: {total_artifacts}")
    print(f"✓ Artifacts uploaded to storage: {artifacts_with_gcs}/{total_artifacts}")
    print(f"✓ Artifacts with ALL uploads succeeded: {artifacts_all_uploads_succeeded}/{total_artifacts}")

    if artifacts_with_gcs < total_artifacts:
        print(f"⚠️  Artifacts NOT uploaded: {total_artifacts - artifacts_with_gcs}")

    return results

def generate_report(articles, results):
    """Generate comprehensive verification report."""
    print("\n" + "="*80)
    print("COMPREHENSIVE VERIFICATION REPORT")
    print("="*80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"CSV File: missing_urls.csv")
    print(f"Total Articles: {len(articles)}")

    # PostgreSQL Summary
    in_postgres = sum(1 for r in results if r['in_postgres'])
    print(f"\n{'='*80}")
    print("POSTGRESQL STATUS")
    print(f"{'='*80}")
    print(f"✓ In PostgreSQL: {in_postgres}/{len(articles)} ({in_postgres/len(articles)*100:.1f}%)")
    print(f"✗ Missing: {len(articles) - in_postgres}/{len(articles)}")

    # Check for item_id mismatches
    id_mismatches = []
    for r in results:
        if r['in_postgres'] and r['postgres_data']['item_id'] != r['original_item_id']:
            id_mismatches.append(r)

    if id_mismatches:
        print(f"\n⚠️  ITEM_ID MISMATCHES: {len(id_mismatches)}")
        print("Articles saved with different item_ids:")
        for r in id_mismatches:
            print(f"  Original: {r['original_item_id']}")
            print(f"  In DB:    {r['postgres_data']['item_id']}")
            print(f"  URL:      {r['url'][:80]}...")
            print()

    # Archive Artifacts Summary
    total_with_artifacts = sum(1 for r in results if r['in_postgres'] and len(r.get('artifacts', [])) > 0)
    print(f"\n{'='*80}")
    print("ARCHIVE ARTIFACTS STATUS")
    print(f"{'='*80}")
    print(f"✓ Articles with artifacts: {total_with_artifacts}/{in_postgres}")

    # Archiver breakdown
    archiver_stats = defaultdict(lambda: {'total': 0, 'success': 0, 'failed': 0, 'pending': 0})
    for r in results:
        if not r['in_postgres']:
            continue
        for artifact in r.get('artifacts', []):
            archiver = artifact['archiver']
            archiver_stats[archiver]['total'] += 1
            if artifact['success']:
                archiver_stats[archiver]['success'] += 1
            elif artifact['status'] == 'pending':
                archiver_stats[archiver]['pending'] += 1
            else:
                archiver_stats[archiver]['failed'] += 1

    if archiver_stats:
        print("\nBy Archiver:")
        for archiver, stats in sorted(archiver_stats.items()):
            print(f"  {archiver}:")
            print(f"    Total: {stats['total']}")
            print(f"    ✓ Success: {stats['success']}")
            print(f"    ⏳ Pending: {stats['pending']}")
            print(f"    ✗ Failed: {stats['failed']}")

    # GCS Upload Summary
    total_artifacts = sum(len(r.get('artifacts', [])) for r in results if r['in_postgres'])
    artifacts_with_gcs = sum(
        sum(1 for a in r.get('artifacts', []) if a['uploaded_to_storage'])
        for r in results if r['in_postgres']
    )
    artifacts_all_succeeded = sum(
        sum(1 for a in r.get('artifacts', []) if a['all_uploads_succeeded'])
        for r in results if r['in_postgres']
    )

    print(f"\n{'='*80}")
    print("GCS UPLOAD STATUS")
    print(f"{'='*80}")
    print(f"Total artifacts: {total_artifacts}")
    print(f"✓ Uploaded to storage: {artifacts_with_gcs}/{total_artifacts} ({artifacts_with_gcs/total_artifacts*100 if total_artifacts > 0 else 0:.1f}%)")
    print(f"✓ All uploads succeeded: {artifacts_all_succeeded}/{total_artifacts} ({artifacts_all_succeeded/total_artifacts*100 if total_artifacts > 0 else 0:.1f}%)")

    # Detailed Status
    print(f"\n{'='*80}")
    print("DETAILED ARTICLE STATUS")
    print(f"{'='*80}")

    # Group by status
    fully_synced = []
    partial_synced = []
    not_synced = []
    id_changed = []

    for r in results:
        if not r['in_postgres']:
            not_synced.append(r)
        elif r['postgres_data']['item_id'] != r['original_item_id']:
            id_changed.append(r)
        else:
            artifacts = r.get('artifacts', [])
            if artifacts and all(a['all_uploads_succeeded'] for a in artifacts):
                fully_synced.append(r)
            else:
                partial_synced.append(r)

    print(f"\n✓ FULLY SYNCED: {len(fully_synced)}")
    print(f"  (In PostgreSQL, has artifacts, all GCS uploads succeeded)")

    print(f"\n⚠️  PARTIALLY SYNCED: {len(partial_synced)}")
    print(f"  (In PostgreSQL but missing artifacts or GCS uploads)")
    if partial_synced and len(partial_synced) <= 10:
        for r in partial_synced:
            print(f"    {r['original_item_id']}: {r['url'][:60]}...")
            artifacts = r.get('artifacts', [])
            if not artifacts:
                print(f"      No artifacts")
            else:
                for a in artifacts:
                    status = "✓" if a['all_uploads_succeeded'] else "✗"
                    print(f"      {status} {a['archiver']}: {a['status']}")

    print(f"\n⚠️  ITEM_ID CHANGED: {len(id_changed)}")
    print(f"  (Saved with different item_id - likely got pocket_* ID)")
    if id_changed and len(id_changed) <= 10:
        for r in id_changed:
            print(f"    {r['original_item_id']} → {r['postgres_data']['item_id']}")

    print(f"\n✗ NOT SYNCED: {len(not_synced)}")
    print(f"  (Not found in PostgreSQL)")
    if not_synced and len(not_synced) <= 10:
        for r in not_synced:
            print(f"    {r['original_item_id']}: {r['url'][:60]}...")

    # Overall Success Rate
    print(f"\n{'='*80}")
    print("OVERALL SUCCESS RATE")
    print(f"{'='*80}")
    success_rate = len(fully_synced) / len(articles) * 100 if articles else 0
    print(f"✓ {len(fully_synced)}/{len(articles)} articles fully synced ({success_rate:.1f}%)")

    if success_rate == 100:
        print("\n🎉 ALL ARTICLES SUCCESSFULLY SYNCED!")
    elif success_rate >= 90:
        print("\n✓ Most articles synced successfully")
    elif success_rate >= 50:
        print("\n⚠️  Partial sync - investigation needed")
    else:
        print("\n❌ Sync largely failed - immediate action required")

    return {
        'total': len(articles),
        'fully_synced': len(fully_synced),
        'partial_synced': len(partial_synced),
        'id_changed': len(id_changed),
        'not_synced': len(not_synced),
        'success_rate': success_rate
    }

def save_detailed_report(results, summary):
    """Save detailed results to a file."""
    report_path = Path("sync_verification_report.txt")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("ARTICLE SYNC VERIFICATION REPORT\n")
        f.write("="*80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total Articles: {summary['total']}\n")
        f.write(f"Fully Synced: {summary['fully_synced']}\n")
        f.write(f"Partial Synced: {summary['partial_synced']}\n")
        f.write(f"ID Changed: {summary['id_changed']}\n")
        f.write(f"Not Synced: {summary['not_synced']}\n")
        f.write(f"Success Rate: {summary['success_rate']:.1f}%\n")
        f.write("\n" + "="*80 + "\n")
        f.write("DETAILED ARTICLE DATA\n")
        f.write("="*80 + "\n\n")

        for r in results:
            f.write(f"Item ID: {r['original_item_id']}\n")
            f.write(f"URL: {r['url']}\n")
            f.write(f"In PostgreSQL: {r['in_postgres']}\n")

            if r['in_postgres']:
                pg = r['postgres_data']
                f.write(f"  DB Item ID: {pg['item_id']}\n")
                f.write(f"  DB ID: {pg['id']}\n")
                f.write(f"  Created: {pg['created_at']}\n")
                f.write(f"  Size: {pg['total_size_bytes']} bytes\n")

                artifacts = r.get('artifacts', [])
                f.write(f"  Artifacts: {len(artifacts)}\n")
                for a in artifacts:
                    f.write(f"    - {a['archiver']}:\n")
                    f.write(f"        Success: {a['success']}\n")
                    f.write(f"        Status: {a['status']}\n")
                    f.write(f"        Uploaded: {a['uploaded_to_storage']}\n")
                    f.write(f"        All Uploads Succeeded: {a['all_uploads_succeeded']}\n")
                    f.write(f"        Size: {a['size_bytes']} bytes\n")

            f.write("\n" + "-"*80 + "\n\n")

    print(f"\n✓ Detailed report saved to: {report_path}")

def main():
    """Main execution."""
    try:
        print("="*80)
        print("ARTICLE SYNC VERIFICATION")
        print("="*80)
        print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['name']}")

        # Load CSV
        csv_path = Path("missing_urls.csv")
        if not csv_path.exists():
            print(f"❌ Error: {csv_path} not found!")
            sys.exit(1)

        print(f"Loading articles from: {csv_path}")
        articles = load_csv_articles(csv_path)
        print(f"✓ Loaded {len(articles)} articles")

        # Connect to database
        print("\nConnecting to database...")
        engine = create_db_connection()
        print("✓ Connected!")

        # Check PostgreSQL
        results = check_postgres_entries(engine, articles)

        # Check artifacts
        results = check_archive_artifacts(engine, results)

        # Check GCS uploads
        results = check_gcs_uploads(results)

        # Generate report
        summary = generate_report(articles, results)

        # Save detailed report
        save_detailed_report(results, summary)

        print("\n" + "="*80)
        print("VERIFICATION COMPLETE")
        print("="*80)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
