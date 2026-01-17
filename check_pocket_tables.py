#!/usr/bin/env python3
"""
Script to investigate Pocket-related tables and their relationship to archived_urls.
"""
from sqlalchemy import create_engine, text, inspect
from urllib.parse import quote_plus
import sys
import io

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
    engine = create_engine(url, pool_pre_ping=True)
    return engine

def inspect_pocket_tables(engine):
    """Inspect Pocket-related tables."""
    print("="*80)
    print("POCKET-RELATED TABLES INVESTIGATION")
    print("="*80)

    pocket_tables = [
        'pocketarticle',
        'pocketauthors',
        'pocketimages',
        'pocketvideos',
        'pockettags'
    ]

    inspector = inspect(engine)

    with engine.connect() as conn:
        for table_name in pocket_tables:
            print(f"\n{'='*80}")
            print(f"TABLE: {table_name}")
            print(f"{'='*80}")

            # Check if table exists
            if table_name not in inspector.get_table_names():
                print(f"Table {table_name} does not exist")
                continue

            # Get column information
            columns = inspector.get_columns(table_name)
            print(f"\nColumns ({len(columns)}):")
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")

            # Get row count
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name};"))
            count = result.scalar()
            print(f"\nTotal rows: {count}")

            if count > 0:
                # Get sample data
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 3;"))
                print("\nSample data (first 3 rows):")
                print("-" * 80)

                for i, row in enumerate(result, 1):
                    print(f"\nRow {i}:")
                    for idx, col in enumerate(columns):
                        value = row[idx]
                        if value is not None and len(str(value)) > 100:
                            value_str = str(value)[:97] + "..."
                        else:
                            value_str = str(value)
                        print(f"  {col['name']}: {value_str}")

def check_pocket_id_origins(engine):
    """Check where pocket_* IDs are coming from."""
    print("\n" + "="*80)
    print("CHECKING pocket_* ID ORIGINS IN archived_urls")
    print("="*80)

    with engine.connect() as conn:
        # Get all pocket_* entries with full details
        result = conn.execute(text("""
            SELECT
                id,
                item_id,
                url,
                name,
                created_at,
                total_size_bytes
            FROM archived_urls
            WHERE item_id LIKE 'pocket_%'
            ORDER BY created_at DESC;
        """))

        print("\nAll entries with pocket_* IDs:")
        print("-" * 120)

        for row in result:
            print(f"\nID: {row.id}")
            print(f"  item_id: {row.item_id}")
            print(f"  url: {row.url}")
            print(f"  name: {row.name}")
            print(f"  created_at: {row.created_at}")
            print(f"  total_size_bytes: {row.total_size_bytes}")

        # Check if these IDs exist in pocketarticle table
        print("\n" + "="*80)
        print("CHECKING IF pocket_* IDs EXIST IN pocketarticle TABLE")
        print("="*80)

        # Just check if any pocket_* IDs match entries in pocketarticle
        result = conn.execute(text("""
            SELECT COUNT(*) as match_count
            FROM archived_urls au
            INNER JOIN pocketarticle pa ON au.item_id = pa."itemId"
            WHERE au.item_id LIKE 'pocket_%';
        """))

        match_count = result.scalar()

        print(f"\nNumber of pocket_* IDs that match pocketarticle.itemId: {match_count}")

        if match_count > 0:
            print("⚠️  Some pocket_* IDs DO exist in pocketarticle table!")
        else:
            print("✓ None of the pocket_* IDs exist in pocketarticle table")
            print("  This suggests they are artificial IDs, not real Pocket item IDs")

def check_recent_saves(engine):
    """Check recent saves to see the pattern."""
    print("\n" + "="*80)
    print("CHECKING RECENT SAVE PATTERNS")
    print("="*80)

    with engine.connect() as conn:
        # Get recent entries grouped by item_id pattern
        result = conn.execute(text("""
            SELECT
                CASE
                    WHEN item_id LIKE 'pocket_%' THEN 'pocket_*'
                    WHEN item_id ~ '^[a-zA-Z0-9]{14}$' THEN 'short_id'
                    ELSE 'other'
                END as id_type,
                COUNT(*) as count,
                MIN(created_at) as first_seen,
                MAX(created_at) as last_seen
            FROM archived_urls
            GROUP BY id_type
            ORDER BY last_seen DESC;
        """))

        print("\nID patterns in archived_urls:")
        print("-" * 80)
        print(f"{'ID Type':<20} {'Count':<10} {'First Seen':<30} {'Last Seen':<30}")
        print("-" * 80)

        for row in result:
            print(f"{row.id_type:<20} {row.count:<10} {str(row.first_seen):<30} {str(row.last_seen):<30}")

        # Check when pocket_* IDs started appearing
        result = conn.execute(text("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as count
            FROM archived_urls
            WHERE item_id LIKE 'pocket_%'
            GROUP BY DATE(created_at)
            ORDER BY date;
        """))

        print("\nPocket_* IDs by date:")
        print("-" * 40)
        print(f"{'Date':<20} {'Count':<10}")
        print("-" * 40)

        for row in result:
            print(f"{str(row.date):<20} {row.count:<10}")

def main():
    """Main execution."""
    try:
        print("Connecting to database...")
        engine = create_db_connection()
        print("✓ Connected!\n")

        inspect_pocket_tables(engine)
        check_pocket_id_origins(engine)
        check_recent_saves(engine)

        print("\n" + "="*80)
        print("Investigation complete!")
        print("="*80)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
