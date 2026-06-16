"""One-time migration script: SQLite → PostgreSQL

Run this from Render's web shell (or locally with DATABASE_URL set to your Render DB):
    python migrate_to_postgres.py

This will:
1. Read the local SQLite database (data/uk49_lunchtime.db)
2. Insert all data into the Render PostgreSQL database
3. Reset sequences so new inserts get correct IDs

Requirements:
    - DATABASE_URL env var must be set (pointing to your Render PostgreSQL)
    - Local SQLite file must exist at data/uk49_lunchtime.db
"""

import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Get PostgreSQL connection string
raw_url = os.getenv("DATABASE_URL", "")
if not raw_url:
    print("ERROR: DATABASE_URL not set! Set it to your Render PostgreSQL URL.")
    print("Example: export DATABASE_URL=postgresql://user:pass@host:5432/dbname")
    exit(1)

if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

# Local SQLite path
sqlite_path = os.getenv("SQLITE_PATH", "data/uk49_lunchtime.db")

if not os.path.exists(sqlite_path):
    print(f"ERROR: SQLite file not found at {sqlite_path}")
    print("If running from Render shell, you may need to upload the file first.")
    print("Alternative: run this locally with DATABASE_URL set to your Render DB.")
    exit(1)


def migrate():
    print("=" * 50)
    print("UK49 Bot: SQLite → PostgreSQL Migration")
    print("=" * 50)
    print(f"SQLite source: {sqlite_path}")
    print(f"PostgreSQL target: {raw_url[:50]}...")
    print()

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(raw_url)
    pg_cursor = pg_conn.cursor()

    # Tables to migrate (in order, respecting FKs)
    tables = [
        "draws",
        "predictions",
        "accuracy",
        "stats_snapshots",
        "audit_log",
    ]

    total_rows = 0

    for table in tables:
        print(f"\nMigrating table: {table}")

        # Get SQLite data
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()

        if not rows:
            print(f"  No data in {table}")
            continue

        # Get column names
        columns = [description[0] for description in sqlite_cursor.description]
        print(f"  Columns: {', '.join(columns)}")
        print(f"  Rows to migrate: {len(rows)}")

        # Build INSERT query
        placeholders = ",".join(["%s"] * len(columns))
        columns_str = ",".join(columns)
        insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"

        # Insert rows
        for row in rows:
            values = tuple(row)
            try:
                pg_cursor.execute(insert_sql, values)
            except psycopg2.IntegrityError as e:
                pg_conn.rollback()
                print(f"  ⚠ Duplicate skipped: {e}")
                continue
            except Exception as e:
                pg_conn.rollback()
                print(f"  ❌ Error: {e}")
                continue

        pg_conn.commit()
        total_rows += len(rows)
        print(f"  ✅ Migrated {len(rows)} rows")

    # Migrate state.json
    state_path = "data/state.json"
    if os.path.exists(state_path):
        import json
        with open(state_path, "r") as f:
            state = json.load(f)
        pg_cursor.execute(
            """
            INSERT INTO bot_state (id, state)
            VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                updated_at = CURRENT_TIMESTAMP
        """,
            (json.dumps(state),),
        )
        pg_conn.commit()
        print(f"\n✅ Migrated state.json")
    else:
        print(f"\n⚠ No state.json found at {state_path}")

    # Reset sequences
    print("\nResetting sequences...")
    for table in tables:
        pg_cursor.execute(f"SELECT MAX(id) FROM {table}")
        max_id = pg_cursor.fetchone()[0] or 0
        pg_cursor.execute(f"SELECT setval('{table}_id_seq', {max_id}, true)")
        pg_conn.commit()
        print(f"  {table}_id_seq set to {max_id}")

    # Close connections
    sqlite_conn.close()
    pg_conn.close()

    print("\n" + "=" * 50)
    print(f"Migration complete! Total rows migrated: {total_rows}")
    print("You can now delete the SQLite file and state.json if desired.")
    print("=" * 50)


if __name__ == "__main__":
    migrate()
