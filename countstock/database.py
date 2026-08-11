from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from kivy.app import App
from kivy.utils import platform

DB_NAME = "countstock_inventory.db"
SYNC_PENDING = "PENDING"
SYNCED = "SYNCED"


def get_db_path() -> str:
    if platform == "android":
        return os.path.join(App.get_running_app().user_data_dir, DB_NAME)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)


def connect():
    conn = sqlite3.connect(get_db_path(), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    """Create the CountStock database for a clean installation."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS db_config (
                branch_name TEXT,
                iis_server_ip TEXT,
                db_server_ip TEXT,
                db_name TEXT,
                db_user TEXT,
                db_password TEXT,
                count_month TEXT
            );

            CREATE TABLE IF NOT EXISTS countstock_staff (
                staff_code TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS main_products (
                barcode TEXT PRIMARY KEY,
                product_code TEXT,
                product_name TEXT,
                dept TEXT,
                count_month TEXT,
                unit TEXT
            );

            CREATE TABLE IF NOT EXISTS countstock_scan_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT NOT NULL,
                staff_name TEXT NOT NULL,
                product_code TEXT NOT NULL,
                scanned_value TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                scan_date TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'PENDING',
                synced_at TEXT,
                sync_scan_data INTEGER NOT NULL DEFAULT 0,
                sync_scan_slottag INTEGER NOT NULL DEFAULT 0,
                synced_scan_data_at TEXT,
                synced_scan_slottag_at TEXT
            );

            CREATE INDEX IF NOT EXISTS ix_main_products_code
                ON main_products(product_code);
            CREATE INDEX IF NOT EXISTS ix_countstock_sync_status
                ON countstock_scan_data(sync_status, id);
            CREATE INDEX IF NOT EXISTS ix_countstock_lookup
                ON countstock_scan_data(
                    location, product_code, scanned_value, sync_status
                );
            """
        )



def get_config():
    with connect() as conn:
        row = conn.execute("""
            SELECT branch_name, db_server_ip, db_name, db_user,
                   db_password, count_month, iis_server_ip
            FROM db_config LIMIT 1
        """).fetchone()
        return dict(row) if row else None


def save_config(item: dict, iis_ip: str):
    with connect() as conn:
        conn.execute("DELETE FROM db_config")
        conn.execute("""
            INSERT INTO db_config(
                branch_name, iis_server_ip, db_server_ip, db_name,
                db_user, db_password, count_month
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("branch_name", ""), iis_ip,
            item.get("db_server_ip", ""), item.get("db_name", ""),
            item.get("db_user", ""), item.get("db_password", ""),
            item.get("count_month", "")
        ))


def replace_staff(staff_list):
    """เก็บ Staff config กลางชุดเดียวสำหรับทุกสาขา."""
    values = []
    seen = set()
    for value in staff_list or []:
        code = str(value or "").strip()
        if code and code not in seen:
            seen.add(code)
            values.append((code,))
    with connect() as conn:
        conn.execute("DELETE FROM countstock_staff")
        if values:
            conn.executemany(
                "INSERT INTO countstock_staff(staff_code) VALUES (?)", values
            )
    return len(values)


def get_staff_list():
    with connect() as conn:
        return [
            row["staff_code"]
            for row in conn.execute(
                "SELECT staff_code FROM countstock_staff ORDER BY staff_code"
            ).fetchall()
        ]


def replace_products(items: list[dict]) -> int:
    rows = []
    for item in items:
        if isinstance(item, dict):
            barcode = str(item.get("barcode") or "").strip()
            product_code = str(item.get("product_code") or "").strip()
            if not barcode:
                continue
            rows.append((
                barcode, product_code,
                item.get("product_name") or "",
                item.get("Dept") or item.get("dept") or "",
                item.get("CountMonth") or item.get("count_month") or "",
                item.get("unit") or ""
            ))
        else:
            rows.append(tuple(item[:6]))
    with connect() as conn:
        conn.execute("DELETE FROM main_products")
        conn.executemany("""
            INSERT OR REPLACE INTO main_products(
                barcode, product_code, product_name, dept, count_month, unit
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, rows)
    return len(rows)


def get_product_stats():
    with connect() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS barcode_count,
                   COUNT(DISTINCT product_code) AS product_count
            FROM main_products
        """).fetchone()
        return {
            "barcode_count": int(row["barcode_count"] or 0),
            "product_count": int(row["product_count"] or 0),
        }


def find_product(value: str):
    value = value.strip()
    with connect() as conn:
        row = conn.execute("""
            SELECT product_code, product_name, unit, barcode
            FROM main_products WHERE barcode = ? LIMIT 1
        """, (value,)).fetchone()
        if not row:
            row = conn.execute("""
                SELECT product_code, product_name, unit, barcode
                FROM main_products WHERE TRIM(product_code) = ? LIMIT 1
            """, (value,)).fetchone()
        return dict(row) if row else None


def add_or_increment(location: str, staff: str, product_code: str, scanned_value: str):
    """Increment only an unsynced row; synced history remains immutable."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        row = conn.execute("""
            SELECT id, qty
            FROM countstock_scan_data
            WHERE location=? AND product_code=? AND scanned_value=?
              AND sync_status=?
            ORDER BY id DESC LIMIT 1
        """, (location, product_code, scanned_value, SYNC_PENDING)).fetchone()
        if row:
            qty = int(row["qty"]) + 1
            conn.execute("""
                UPDATE countstock_scan_data
                SET qty=?, staff_name=?, scan_date=?
                WHERE id=?
            """, (qty, staff, now, row["id"]))
            return qty, True

        conn.execute("""
            INSERT INTO countstock_scan_data(
                location, staff_name, product_code, scanned_value,
                qty, scan_date, sync_status, synced_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
        """, (location, staff, product_code, scanned_value, now, SYNC_PENDING))
        return 1, False


def recent(limit=10):
    with connect() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT s.id, s.location, s.staff_name, s.product_code,
                   s.scanned_value, s.qty, s.scan_date, s.sync_status,
                   s.sync_scan_data, s.sync_scan_slottag,
                   COALESCE((
                       SELECT p.product_name
                       FROM main_products p
                       WHERE TRIM(p.product_code) = TRIM(s.product_code)
                       ORDER BY p.rowid
                       LIMIT 1
                   ), '') AS product_name,
                   COALESCE((
                       SELECT p.unit
                       FROM main_products p
                       WHERE TRIM(p.product_code) = TRIM(s.product_code)
                       ORDER BY p.rowid
                       LIMIT 1
                   ), '') AS unit
            FROM countstock_scan_data s
            ORDER BY s.id DESC LIMIT ?
        """, (limit,)).fetchall()]


def get_scan_stats():
    with connect() as conn:
        row = conn.execute("""
            SELECT COUNT(*) AS total_count,
                   SUM(CASE WHEN sync_scan_data=1 OR sync_scan_slottag=1
                            THEN 1 ELSE 0 END) AS synced_count,
                   SUM(CASE WHEN sync_scan_data=0 AND sync_scan_slottag=0
                            THEN 1 ELSE 0 END) AS pending_count,
                   SUM(CASE WHEN sync_scan_data=1 THEN 1 ELSE 0 END) AS scan_data_count,
                   SUM(CASE WHEN sync_scan_slottag=1 THEN 1 ELSE 0 END) AS slottag_count,
                   COALESCE(SUM(qty), 0) AS total_qty
            FROM countstock_scan_data
        """).fetchone()
        return {
            "total_count": int(row["total_count"] or 0),
            "synced_count": int(row["synced_count"] or 0),
            "pending_count": int(row["pending_count"] or 0),
            "scan_data_count": int(row["scan_data_count"] or 0),
            "slottag_count": int(row["slottag_count"] or 0),
            "total_qty": int(row["total_qty"] or 0),
        }


def _target_column(table_name: str):
    normalized = str(table_name or "").strip().lower()
    if normalized == "countstock_scan_data":
        return "sync_scan_data", "synced_scan_data_at"
    if normalized == "countstock_scan_slottag":
        return "sync_scan_slottag", "synced_scan_slottag_at"
    raise ValueError("ชื่อตาราง Export ไม่ถูกต้อง")


def export_rows(table_name: str):
    """Return rows not yet exported to the selected destination."""
    status_column, _ = _target_column(table_name)
    with connect() as conn:
        return [dict(r) for r in conn.execute(f"""
            SELECT id, location, staff_name, product_code,
                   scanned_value AS barcode, qty, scan_date
            FROM countstock_scan_data
            WHERE COALESCE(sync_scan_data, 0) = 0
              AND COALESCE(sync_scan_slottag, 0) = 0
            ORDER BY id
        """).fetchall()]


def mark_rows_synced(row_ids, table_name: str):
    ids = [int(value) for value in row_ids if int(value) > 0]
    if not ids:
        return 0
    status_column, date_column = _target_column(table_name)
    placeholders = ",".join("?" for _ in ids)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        cursor = conn.execute(
            f"UPDATE countstock_scan_data "
            f"SET {status_column}=1, {date_column}=?, "
            f"    sync_status='SYNCED', synced_at=? "
            f"WHERE id IN ({placeholders}) AND COALESCE({status_column},0)=0",
            [now, now] + ids,
        )
        return int(cursor.rowcount or 0)


def row_has_been_synced(row: dict) -> bool:
    return bool(
        int(row.get("sync_scan_data") or 0)
        or int(row.get("sync_scan_slottag") or 0)
        or str(row.get("sync_status") or "").upper() == SYNCED
    )


def update_pending_location(row_id: int, new_location: str):
    new_location = str(new_location or "").strip()
    if not new_location:
        raise ValueError("กรุณากรอก Location ใหม่")

    with connect() as conn:
        source = conn.execute("""
            SELECT id, product_code, scanned_value, qty, sync_status
            FROM countstock_scan_data WHERE id=?
        """, (int(row_id),)).fetchone()
        if not source:
            raise ValueError("ไม่พบรายการที่ต้องการแก้ไข")
        if str(source["sync_status"]).upper() == SYNCED:
            raise ValueError("รายการที่ Sync แล้วไม่สามารถแก้ Location ได้")

        target = conn.execute("""
            SELECT id, qty FROM countstock_scan_data
            WHERE id<>? AND location=? AND product_code=? AND scanned_value=?
              AND sync_status=?
            ORDER BY id DESC LIMIT 1
        """, (
            int(row_id), new_location, source["product_code"],
            source["scanned_value"], SYNC_PENDING,
        )).fetchone()

        if target:
            conn.execute(
                "UPDATE countstock_scan_data SET qty=qty+? WHERE id=?",
                (int(source["qty"]), int(target["id"])),
            )
            conn.execute("DELETE FROM countstock_scan_data WHERE id=?", (int(row_id),))
        else:
            conn.execute(
                "UPDATE countstock_scan_data SET location=? WHERE id=?",
                (new_location, int(row_id)),
            )


def delete_pending_row(row_id: int):
    with connect() as conn:
        row = conn.execute(
            "SELECT sync_status FROM countstock_scan_data WHERE id=?",
            (int(row_id),),
        ).fetchone()
        if not row:
            raise ValueError("ไม่พบรายการที่ต้องการลบ")
        if str(row["sync_status"]).upper() == SYNCED:
            raise ValueError("รายการที่ Sync แล้วไม่สามารถลบได้")
        conn.execute("DELETE FROM countstock_scan_data WHERE id=?", (int(row_id),))


def clear_scans(only_unsynced=False):
    with connect() as conn:
        if only_unsynced:
            conn.execute("DELETE FROM countstock_scan_data WHERE sync_status<>'SYNCED'")
        else:
            conn.execute("DELETE FROM countstock_scan_data")
