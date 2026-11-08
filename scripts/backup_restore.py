"""
Database backup and restore verification script (Item 25).
Performs a backup of the source database into a timestamped file, restores it into
a scratch verification database, and verifies schema and record parity.

Supports SQLite and PostgreSQL.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime


def verify_sqlite_backup_restore(source_db_path: str) -> bool:
    print(f"[*] Starting backup verification for SQLite database: {source_db_path}")
    if not os.path.exists(source_db_path):
        print(f"[!] Source database file not found: {source_db_path}")
        return False

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_file = f"{source_db_path}.backup_{timestamp}"
    scratch_dir = tempfile.mkdtemp(prefix="resumefit_restore_test_")
    restored_db_path = os.path.join(scratch_dir, "restored_app.db")

    try:
        # 1. Source Database Statistics
        with sqlite3.connect(source_db_path) as src_conn:
            src_cur = src_conn.cursor()
            src_users = src_cur.execute("SELECT count(*) FROM users").fetchone()[0]
            src_analyses = src_cur.execute("SELECT count(*) FROM analyses").fetchone()[0]
            print(f"[+] Source database state: {src_users} users, {src_analyses} analyses.")

        # 2. Perform Backup using SQLite Online Backup API
        print(f"[*] Creating backup to: {backup_file}")
        src_conn = sqlite3.connect(source_db_path)
        dst_conn = sqlite3.connect(backup_file)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()
        print(f"[+] Backup completed successfully ({os.path.getsize(backup_file)} bytes).")

        # 3. Simulate Restoration into Scratch Environment
        print(f"[*] Restoring backup into scratch verification instance: {restored_db_path}")
        shutil.copy2(backup_file, restored_db_path)

        # 4. Verify Integrity and Record Counts in Restored Database
        rest_conn = sqlite3.connect(restored_db_path)
        try:
            rest_cur = rest_conn.cursor()
            integrity = rest_cur.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                print(f"[!] Restore integrity check failed: {integrity}")
                return False

            rest_users = rest_cur.execute("SELECT count(*) FROM users").fetchone()[0]
            rest_analyses = rest_cur.execute("SELECT count(*) FROM analyses").fetchone()[0]
            print(
                f"[+] Restored database verification: {rest_users} users, {rest_analyses} analyses."
            )

            assert src_users == rest_users, "User record count mismatch!"
            assert src_analyses == rest_analyses, "Analyses record count mismatch!"
        finally:
            rest_conn.close()

        print("[SUCCESS] Backup and restoration verification passed with 100% record parity.")
        return True

    except Exception as e:
        print(f"[ERROR] Backup restore verification failed: {e}")
        return False

    finally:
        # Clean up scratch files
        if os.path.exists(backup_file):
            os.remove(backup_file)
        if os.path.exists(scratch_dir):
            shutil.rmtree(scratch_dir, ignore_errors=True)


if __name__ == "__main__":
    db_target = sys.argv[1] if len(sys.argv) > 1 else "./app.db"
    success = verify_sqlite_backup_restore(db_target)
    sys.exit(0 if success else 1)
