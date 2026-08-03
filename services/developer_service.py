"""
=========================================================
Project : HWK_StockV1
File    : services/developer_service.py
Purpose : Developer utilities for local SQLite test data
=========================================================
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Iterable


class DeveloperService:
    """ล้างข้อมูลทดสอบใน SQLite โดยไม่ลบค่าตั้งค่าเครื่อง/API"""

    DATA_TABLES: tuple[str, ...] = (
        "tb_sync_queue",
        "tb_audit_history",
        "tbt_count_history",
        "tb_plan_detail",
        "tb_barcode",
        "tb_location",
        "tb_item",
        "tb_download_log",
        "tb_plan",
    )

    def __init__(self, db):
        self.db = db

    def reset_local_database(self) -> Dict[str, int]:
        """
        ล้างข้อมูลการทำงานในเครื่องทั้งหมด แต่คง app_config ไว้เพื่อรักษา:
        - device_id
        - URL และค่าตั้งค่า API
        - ค่าตั้งค่าเครื่อง
        """
        connection = self.db.get_connection()
        deleted: Dict[str, int] = {}

        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 30000")
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")

            existing_tables = self._existing_tables(connection)

            for table_name in self.DATA_TABLES:
                if table_name not in existing_tables:
                    deleted[table_name] = 0
                    continue

                cursor = connection.execute(
                    f'DELETE FROM "{table_name}"'
                )
                deleted[table_name] = max(int(cursor.rowcount or 0), 0)

            # Reset AUTOINCREMENT เฉพาะตารางที่ถูกล้าง
            if "sqlite_sequence" in existing_tables:
                placeholders = ",".join("?" for _ in self.DATA_TABLES)
                connection.execute(
                    f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                    self.DATA_TABLES,
                )

            # ลบ Batch ปัจจุบัน แต่คง device_id และ Config อื่นไว้
            if "app_config" in existing_tables:
                connection.execute(
                    "DELETE FROM app_config WHERE config_key LIKE 'sync_batch_guid_plan_%'"
                )

            connection.commit()
            connection.execute("PRAGMA foreign_keys = ON")

            # VACUUM ต้องรันนอก Transaction
            try:
                connection.execute("VACUUM")
            except sqlite3.DatabaseError:
                # การล้างข้อมูลถือว่าสำเร็จ แม้ VACUUM จะทำไม่ได้ในบาง runtime
                pass

            return deleted

        except Exception:
            try:
                connection.rollback()
            finally:
                try:
                    connection.execute("PRAGMA foreign_keys = ON")
                except Exception:
                    pass
            raise
        finally:
            connection.close()

    @staticmethod
    def _existing_tables(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
        return {str(row[0]) for row in rows}
