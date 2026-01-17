#!/usr/bin/env python3
"""
Script to check PostgreSQL database for pocket_* IDs and investigate data consistency.
"""
from sqlalchemy import create_engine, text, inspect
from urllib.parse import quote_plus
import sys
import io

# Set UTF-8 encoding for stdout on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Database configuration from user
DB_CONFIG = {
    'host': 'postgres.archivist.lol',
    'port': 5432,
    'name': 'postgres',
    'user': 'archivist',
    'password': 'ed83e2f93719'
}

def create_db_connection():
    """Create database connection using provided credentials."""
    user = quote_plus(DB_CONFIG['user'])
    pwd = quote_plus(DB_CONFIG['password'])
    url = f"postgresql+psycopg://{user}:{pwd}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['name']}"

    print(f"Connecting to: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['name']}")
    engine = create_engine(url, pool_pre_ping=True)
    return engine

def list_all_tables(engine):
    """List all tables in the database."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nFound {len(tables)} tables in database:")
    for table in tables:
        print(f"  - {table}")
    return tables

def check_pocket_ids_in_archived_urls(engine):
    """Check for pocket_* pattern in archived_urls table."""
    print("\n" + "="*80)
    print("CHECKING archived_urls TABLE FOR pocket_* PATTERN")
    print("="*80)

    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'archived_urls'
            );
        """))
        table_exists = result.scalar()

        if not table_exists:
            print("❌ archived_urls table does not exist!")
            return

        print("✓ archived_urls table exists\n")

        # Get total count
        result = conn.execute(text("SELECT COUNT(*) FROM archived_urls;"))
        total_count = result.scalar()
        print(f"Total rows in archived_urls: {total_count}")

        # Check for pocket_* pattern in item_id
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM archived_urls
            WHERE item_id LIKE 'pocket_%';
        """))
        pocket_count = result.scalar()
        print(f"Rows with item_id starting with 'pocket_': {pocket_count}")

        if pocket_count > 0:
            print(f"\n⚠️  Found {pocket_count} entries with pocket_* IDs!\n")

            # Get sample entries
            result = conn.execute(text("""
                SELECT id, item_id, url, name, created_at
                FROM archived_urls
                WHERE item_id LIKE 'pocket_%'
                ORDER BY created_at DESC
                LIMIT 10;
            """))

            print("Sample entries with pocket_* IDs:")
            print("-" * 120)
            print(f"{'ID':<8} {'ITEM_ID':<30} {'URL':<50} {'NAME':<20} {'CREATED_AT':<20}")
            print("-" * 120)

            for row in result:
                url_short = row.url[:47] + "..." if len(row.url) > 50 else row.url
                name_short = (row.name[:17] + "...") if row.name and len(row.name) > 20 else (row.name or "")
                print(f"{row.id:<8} {row.item_id:<30} {url_short:<50} {name_short:<20} {str(row.created_at):<20}")
        else:
            print("✓ No entries found with pocket_* pattern in item_id")

        # Check for any NULL item_ids
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM archived_urls
            WHERE item_id IS NULL;
        """))
        null_count = result.scalar()
        print(f"\nRows with NULL item_id: {null_count}")

        # Get sample of recent entries
        print("\nRecent entries (last 10):")
        print("-" * 120)
        result = conn.execute(text("""
            SELECT id, item_id, url, name, created_at
            FROM archived_urls
            ORDER BY created_at DESC
            LIMIT 10;
        """))

        print(f"{'ID':<8} {'ITEM_ID':<30} {'URL':<50} {'NAME':<20} {'CREATED_AT':<20}")
        print("-" * 120)

        for row in result:
            url_short = row.url[:47] + "..." if len(row.url) > 50 else row.url
            name_short = (row.name[:17] + "...") if row.name and len(row.name) > 20 else (row.name or "")
            item_id_display = row.item_id or "<NULL>"
            print(f"{row.id:<8} {item_id_display:<30} {url_short:<50} {name_short:<20} {str(row.created_at):<20}")

def check_all_tables_for_pocket(engine, tables):
    """Check all tables for any columns containing pocket_* pattern."""
    print("\n" + "="*80)
    print("CHECKING ALL TABLES FOR pocket_* PATTERN")
    print("="*80)

    inspector = inspect(engine)

    with engine.connect() as conn:
        for table_name in tables:
            columns = inspector.get_columns(table_name)

            # Look for string/text columns
            text_columns = [col['name'] for col in columns
                          if str(col['type']).lower() in ['text', 'string', 'varchar', 'character varying']]

            if not text_columns:
                continue

            # Check each text column for pocket_* pattern
            for col in text_columns:
                try:
                    result = conn.execute(text(f"""
                        SELECT COUNT(*)
                        FROM {table_name}
                        WHERE {col} LIKE 'pocket_%';
                    """))
                    count = result.scalar()

                    if count > 0:
                        print(f"\n⚠️  Table: {table_name}, Column: {col}")
                        print(f"   Found {count} rows with pocket_* pattern")

                        # Get sample
                        result = conn.execute(text(f"""
                            SELECT {col}
                            FROM {table_name}
                            WHERE {col} LIKE 'pocket_%'
                            LIMIT 5;
                        """))

                        print("   Sample values:")
                        for row in result:
                            print(f"     - {row[0]}")

                except Exception as e:
                    # Skip columns that can't be queried
                    pass

def main():
    """Main execution function."""
    try:
        print("Starting database investigation...")
        print("="*80)

        engine = create_db_connection()
        print("✓ Connection successful!\n")

        # List all tables
        tables = list_all_tables(engine)

        # Check archived_urls specifically
        check_pocket_ids_in_archived_urls(engine)

        # Check all tables
        check_all_tables_for_pocket(engine, tables)

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
