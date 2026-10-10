import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
BACKUP_DIR = BASE_DIR / "backups"
DB_SRC = BASE_DIR / "db.sqlite3"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DB_BACKUP_FILE = BACKUP_DIR / f"db_backup_pre_cleanup_{TIMESTAMP}.sqlite3"
CANONICAL_BACKUP_FILE = BACKUP_DIR / "db_backup_pre_cleanup.sqlite3"
MEDIA_SRC = BASE_DIR / "media" / "evidence"
MEDIA_BACKUP_DIR = BACKUP_DIR / f"media_evidence_backup_{TIMESTAMP}"

def create_and_verify_backup():
    print("=" * 80)
    print("CREATING DATABASE & MEDIA BACKUP")
    print("=" * 80)

    # 1. Ensure backup directory exists
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[1] Target backup directory: {BACKUP_DIR}")

    # 2. Native SQLite Online Backup
    print(f"[2] Backing up SQLite database from {DB_SRC} to {DB_BACKUP_FILE}...")
    src_conn = sqlite3.connect(str(DB_SRC))
    dst_conn = sqlite3.connect(str(DB_BACKUP_FILE))
    
    with dst_conn:
        src_conn.backup(dst_conn, pages=100)
    
    dst_conn.close()
    src_conn.close()

    # Also make a copy as canonical name for convenience
    shutil.copy2(str(DB_BACKUP_FILE), str(CANONICAL_BACKUP_FILE))
    print(f"    Backup created successfully. Size: {DB_BACKUP_FILE.stat().st_size:,} bytes")

    # 3. Verify SQLite Integrity Check
    print("[3] Verifying database integrity...")
    verify_conn = sqlite3.connect(str(DB_BACKUP_FILE))
    cursor = verify_conn.cursor()
    cursor.execute("PRAGMA integrity_check;")
    integrity_result = cursor.fetchone()[0]
    print(f"    PRAGMA integrity_check result: {integrity_result}")
    assert integrity_result == "ok", f"Integrity check failed: {integrity_result}"

    # 4. Compare Table Counts and Row Counts
    src_check = sqlite3.connect(str(DB_SRC))
    src_cur = src_check.cursor()
    
    src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    src_tables = sorted([r[0] for r in src_cur.fetchall()])
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    dst_tables = sorted([r[0] for r in cursor.fetchall()])
    
    assert src_tables == dst_tables, "Table list mismatch between source and backup!"
    print(f"    Table count verified: {len(dst_tables)} tables match exactly.")

    total_rows_src = 0
    total_rows_dst = 0
    for table in src_tables:
        src_cur.execute(f"SELECT COUNT(*) FROM \"{table}\";")
        cnt_src = src_cur.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM \"{table}\";")
        cnt_dst = cursor.fetchone()[0]
        assert cnt_src == cnt_dst, f"Row count mismatch on table {table}: src={cnt_src}, dst={cnt_dst}"
        total_rows_src += cnt_src
        total_rows_dst += cnt_dst

    print(f"    All row counts verified: {total_rows_dst} rows across {len(dst_tables)} tables match 100%.")
    src_check.close()
    verify_conn.close()

    # 5. Media Backup
    if MEDIA_SRC.exists():
        print(f"[4] Backing up media files from {MEDIA_SRC} to {MEDIA_BACKUP_DIR}...")
        shutil.copytree(str(MEDIA_SRC), str(MEDIA_BACKUP_DIR))
        files_cnt = sum(1 for _ in MEDIA_BACKUP_DIR.rglob("*") if _.is_file())
        print(f"    Media backup verified: {files_cnt} files backed up.")
    else:
        print("[4] Media evidence directory does not exist, skipping media backup.")

    print("\n" + "=" * 80)
    print("BACKUP VERIFICATION COMPLETED SUCCESSFULLY (100% OK)")
    print(f"Database Backup: {DB_BACKUP_FILE}")
    print(f"Canonical Backup: {CANONICAL_BACKUP_FILE}")
    if MEDIA_SRC.exists():
        print(f"Media Backup: {MEDIA_BACKUP_DIR}")
    print("=" * 80)
    return True

if __name__ == "__main__":
    create_and_verify_backup()
