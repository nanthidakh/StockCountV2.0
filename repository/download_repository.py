"""
=========================================================
Project : HWK_StockV1
File    : repository/download_repository.py
Download Repository
Save Download Package
(SQLite)
Python 3.11+
=========================================================
"""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from datetime import date, datetime
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
)
DOWNLOAD_MODE_INITIAL = "INITIAL"
DOWNLOAD_MODE_REFRESH = "REFRESH"
# =====================================================
# Exception
# =====================================================
class DownloadRepositoryError(Exception):
    """
    Error ของ Download Repository
    """
    pass
# =====================================================
# Repository
# =====================================================
class DownloadRepository:
    # =====================================================
    # Constructor
    # =====================================================
    def __init__(
        self,
        db,
    ):
        self.db = db
    # =====================================================
    # SQLite Connection
    # =====================================================
    @contextmanager
    def _connection(
        self,
    ) -> Iterator[sqlite3.Connection]:
        connection = None
        should_close = False
        try:
            # ----------------------------
            # SQLiteDB class
            # ----------------------------
            if hasattr(
                self.db,
                "get_connection",
            ):
                connection = self.db.get_connection()
                should_close = True
            elif hasattr(
                self.db,
                "connect",
            ):
                connection = self.db.connect()
                should_close = False
            elif isinstance(
                self.db,
                sqlite3.Connection,
            ):
                connection = self.db
            else:
                raise DownloadRepositoryError(
                    "Database object ไม่รองรับการเชื่อมต่อ"
                )
            if connection is None:
                raise DownloadRepositoryError(
                    "ไม่สามารถเปิด SQLite Connection ได้"
                )
            if not isinstance(
                connection,
                sqlite3.Connection,
            ):
                raise DownloadRepositoryError(
                    "Database Connection ไม่ใช่ sqlite3.Connection"
                )
            connection.row_factory = sqlite3.Row
            connection.execute(
                "PRAGMA foreign_keys = ON"
            )
            connection.execute(
                "PRAGMA busy_timeout = 30000"
            )
            yield connection
        finally:
            if (
                should_close
                and
                connection is not None
            ):
                try:
                    connection.close()
                except Exception:
                    pass
        # =====================================================
    # Save Download Package
    # =====================================================
    def save_download_package(
        self,
        package: dict,
        mode: str = DOWNLOAD_MODE_INITIAL,
    ) -> None:
        """
        บันทึกข้อมูล Download ลง SQLite

        INITIAL:
            ใช้ตอน Download Plan ครั้งแรก
            สามารถล้างข้อมูลเดิมของ Plan ได้

        REFRESH:
            ใช้หลัง Sync Count/Audit
            ห้ามล้าง Local Pending Data
   
        บันทึกข้อมูล Download ทั้ง Package ลง SQLite

        ขั้นตอน:
            1. Validate Package
            2. Prepare Schema
            3. Begin Transaction
            4. INITIAL: ตรวจสอบ Pending และลบข้อมูลเดิม
            5. REFRESH: รักษาข้อมูล Local Pending
            6. Save Plan
            7. Save Items
            8. Save Barcodes
            9. Save Locations
            10. Initial Save หรือ Refresh Details
            11. Save Download Log
            12. Commit
            13. Verify Download
        """
        
        self._validate_package(
            package
        )
                
        plan = package["plan"]
        items = package["items"]
        barcodes = package["barcodes"]
        locations = package["locations"]
        details = package["details"]
        plan_id = self._to_int(
            plan.get("plan_id"),
            "plan.plan_id",
        )

        if mode not in (
            DOWNLOAD_MODE_INITIAL,
            DOWNLOAD_MODE_REFRESH,
        ):
            raise DownloadRepositoryError(
                f"Download mode ไม่ถูกต้อง: {mode}"
            )

        with self._connection() as connection:
            try:

                self._ensure_schema(connection)

                connection.execute("BEGIN IMMEDIATE")

                if mode == DOWNLOAD_MODE_INITIAL:
                    self._validate_initial_download_allowed(
                        connection,
                        plan_id,
                    )
                    self._delete_existing_plan(
                        connection,
                        plan_id,
                    )

                self._save_plan(
                    connection,
                    package["plan"],
                )

                self._save_items(
                    connection,
                    package["items"],
                )

                self._save_barcodes(
                    connection,
                    package["barcodes"],
                )

                self._save_locations(
                    connection,
                    package["locations"],
                )

                if mode == DOWNLOAD_MODE_INITIAL:
                    self._save_details(
                        connection,
                        package["details"],
                    )
                else:
                    self._refresh_details(
                        connection,
                        package["details"],
                    )

                self._save_download_metadata(
                    connection,
                    plan_id,
                )

                connection.commit()
            except Exception as exc:
                connection.rollback()
                if isinstance(
                    exc,
                    DownloadRepositoryError,
                ):
                    raise
                raise DownloadRepositoryError(
                    "บันทึกข้อมูล Download ลง SQLite ไม่สำเร็จ: "
                    f"{exc}"
                ) from exc
            finally:
                try:
                    connection.execute(
                        "PRAGMA foreign_keys = ON"
                    )
                except Exception:
                    pass
        # =================================================
        # Verify After Commit
        # =================================================
        expected_counts = {
            "item_count": len(
                {
                    self._to_int(item.get("item_id"))
                    for item in items
                    if self._to_int(item.get("item_id")) > 0
                }
            ),
            "barcode_count": len(
                {
                    (
                        self._to_int(row.get("item_id")),
                        self._to_text(row.get("barcode")),
                    )
                    for row in barcodes
                    if (
                        self._to_int(row.get("item_id")) > 0
                        and self._to_text(row.get("barcode"))
                    )
                }
            ),
            "location_count": len(
                {
                    (
                        self._to_int(row.get("plan_id")),
                        self._to_int(row.get("location_id")),
                    )
                    for row in locations
                    if (
                        self._to_int(row.get("plan_id")) > 0
                        and self._to_int(row.get("location_id")) > 0
                    )
                }
            ),
            "detail_count": len(
                {
                    self._to_int(row.get("plan_detail_id"))
                    for row in details
                    if self._to_int(
                        row.get("plan_detail_id")
                    ) > 0
                }
            ),
        }
        verify_result = self.verify_download(
            plan_id=plan_id,
            expected_counts=expected_counts,
        )
        return {
            "success": True,
            "message": "บันทึกและตรวจสอบ Plan สำเร็จ",
            "plan_id": plan_id,
            "plan_code": self._to_text(
                plan.get("plan_code")
            ),
            "plan_status": self._to_text(
                plan.get("plan_status")
            ),
            "verified": verify_result["verified"],
            "item_count": verify_result["item_count"],
            "barcode_count": verify_result["barcode_count"],
            "location_count": verify_result["location_count"],
            "detail_count": verify_result["detail_count"],
        }
  
    # =====================================================
    # validate_initial_download
    # =====================================================      
    def _validate_initial_download_allowed(
        self,
        connection: sqlite3.Connection,
        plan_id: int,
    ) -> None:
        """
        ป้องกัน Initial Download ลบข้อมูล Local ที่ยังไม่ได้ Sync

        รองรับ SQLite รุ่นเก่าที่ tb_sync_queue
        อาจยังไม่มี column plan_id
        """

        plan_id = self._to_int(
            plan_id
        )

        if plan_id <= 0:
            raise DownloadRepositoryError(
                "Plan ID สำหรับตรวจสอบข้อมูลรอ Sync ไม่ถูกต้อง"
            )

        # ตารางยังไม่มี ไม่ต้องตรวจ Queue
        if not self._table_exists(
            connection,
            "tb_sync_queue",
        ):
            return

        # SQLite รุ่นเก่ายังไม่มี plan_id
        if not self._column_exists(
            connection,
            "tb_sync_queue",
            "plan_id",
        ):
            return

        pending_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM tb_sync_queue
            WHERE plan_id = ?
            AND UPPER(
                    COALESCE(
                        sync_status,
                        'PENDING'
                    )
                ) IN
                (
                    'PENDING',
                    'SYNCING',
                    'ERROR'
                )
            """,
            (
                plan_id,
            ),
        ).fetchone()[0]

        if pending_count > 0:
            raise DownloadRepositoryError(
                "ไม่สามารถ Download Plan ใหม่ได้ "
                "เนื่องจากมีข้อมูลรอ Sync "
                f"{pending_count:,} รายการ"
            )
        
    # =====================================================
    # Verify Download
    # =====================================================
    def verify_download(
        self,
        plan_id: int,
        expected_counts: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        ตรวจสอบข้อมูล Plan หลังบันทึกลง SQLite
        """
        plan_id = self._to_int(
            plan_id
        )
        if plan_id <= 0:
            raise DownloadRepositoryError(
                "Plan ID สำหรับตรวจสอบไม่ถูกต้อง"
            )
        expected_counts = (
            expected_counts or {}
        )
        with self._connection() as connection:
            plan_row = connection.execute(
                """
                SELECT
                    plan_id,
                    plan_code,
                    plan_status,
                    download_date
                FROM tb_plan
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            if plan_row is None:
                raise DownloadRepositoryError(
                    f"ไม่พบ Plan ID {plan_id} หลัง Download"
                )
            item_count_row = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT d.item_id)
                FROM tb_plan_detail d
                INNER JOIN tb_item i
                    ON i.item_id = d.item_id
                WHERE d.plan_id = ?
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            barcode_count_row = connection.execute(
                """
                SELECT
                    COUNT(*)
                FROM tb_barcode b
                WHERE EXISTS
                (
                    SELECT 1
                    FROM tb_plan_detail d
                    WHERE d.plan_id = ?
                      AND d.item_id = b.item_id
                )
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            location_count_row = connection.execute(
                """
                SELECT
                    COUNT(*)
                FROM tb_location
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            detail_count_row = connection.execute(
                """
                SELECT
                    COUNT(*)
                FROM tb_plan_detail
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            missing_item_count_row = connection.execute(
                """
                SELECT
                    COUNT(*)
                FROM tb_plan_detail d
                LEFT JOIN tb_item i
                    ON i.item_id = d.item_id
                WHERE d.plan_id = ?
                  AND i.item_id IS NULL
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            invalid_detail_count_row = connection.execute(
                """
                SELECT
                    COUNT(*)
                FROM tb_plan_detail
                WHERE plan_id = ?
                  AND
                  (
                      plan_detail_id IS NULL
                      OR plan_detail_id <= 0
                      OR item_id IS NULL
                      OR item_id <= 0
                  )
                """,
                (
                    plan_id,
                ),
            ).fetchone()
            item_count = self._row_count(
                item_count_row
            )
            barcode_count = self._row_count(
                barcode_count_row
            )
            location_count = self._row_count(
                location_count_row
            )
            detail_count = self._row_count(
                detail_count_row
            )
            missing_item_count = self._row_count(
                missing_item_count_row
            )
            invalid_detail_count = self._row_count(
                invalid_detail_count_row
            )
            if detail_count <= 0:
                raise DownloadRepositoryError(
                    "Plan ไม่มีรายละเอียดสินค้าใน SQLite"
                )
            if item_count <= 0:
                raise DownloadRepositoryError(
                    "Plan ไม่มีข้อมูลสินค้าใน SQLite"
                )
            if missing_item_count > 0:
                raise DownloadRepositoryError(
                    "พบ Plan Detail ที่อ้างอิงสินค้าไม่ถูกต้อง "
                    f"{missing_item_count:,} รายการ"
                )
            if invalid_detail_count > 0:
                raise DownloadRepositoryError(
                    "พบ Plan Detail ที่มีข้อมูลหลักไม่ถูกต้อง "
                    f"{invalid_detail_count:,} รายการ"
                )
            self._validate_expected_count(
                name="item",
                actual=item_count,
                expected=expected_counts.get(
                    "item_count"
                ),
            )
            self._validate_expected_count(
                name="barcode",
                actual=barcode_count,
                expected=expected_counts.get(
                    "barcode_count"
                ),
            )
            self._validate_expected_count(
                name="location",
                actual=location_count,
                expected=expected_counts.get(
                    "location_count"
                ),
            )
            self._validate_expected_count(
                name="detail",
                actual=detail_count,
                expected=expected_counts.get(
                    "detail_count"
                ),
            )
            connection.execute(
                """
                UPDATE tb_download_log
                SET status = 'VERIFIED'
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            )
            connection.commit()
            return {
                "verified": True,
                "plan_id": plan_id,
                "plan_code": self._to_text(
                    plan_row["plan_code"]
                ),
                "plan_status": self._to_text(
                    plan_row["plan_status"]
                ),
                "item_count": item_count,
                "barcode_count": barcode_count,
                "location_count": location_count,
                "detail_count": detail_count,
                "missing_item_count": missing_item_count,
                "invalid_detail_count": invalid_detail_count,
            }
    # =====================================================
    # Validate Expected Count
    # =====================================================
    def _validate_expected_count(
        self,
        name: str,
        actual: int,
        expected: Any,
    ) -> None:
        """
        เปรียบเทียบจำนวนข้อมูลจาก Server
        กับจำนวนที่บันทึกจริงใน SQLite
        """
        if expected is None:
            return
        expected_value = self._to_int(
            expected,
            default=-1,
        )
        if expected_value < 0:
            return
        if actual != expected_value:
            raise DownloadRepositoryError(
                f"จำนวน {name} หลังบันทึกไม่ตรงกับ Server "
                f"(Server={expected_value:,}, "
                f"SQLite={actual:,})"
            )
    # =====================================================
    # Row Count Helper
    # =====================================================
    def _row_count(
        self,
        row: Optional[sqlite3.Row],
    ) -> int:
        """
        อ่านค่า COUNT(*) จาก sqlite3.Row
        """
        if row is None:
            return 0
        try:
            return int(
                row[0] or 0
            )
        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            return 0
    
    # =====================================================
    # Table: tb_item
    # =====================================================
    # =====================================================
    # Table: tb_barcode
    # =====================================================
    # =====================================================
    # Table: tb_location
    # =====================================================
    # =====================================================
    # Table: tb_plan_detail
    # =====================================================
    # =====================================================
    # Table: tb_download_log
    # =====================================================
    
    # =====================================================
    # audit_history
    # =====================================================   
    def _create_tb_audit_history(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        เก็บประวัติการ Audit ทุกครั้ง

        qty_audit ใน tb_plan_detail จะเก็บค่าปัจจุบันล่าสุด
        ส่วนตารางนี้เก็บประวัติการตรวจสอบทุกครั้ง
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_audit_history
            (
                audit_history_id INTEGER PRIMARY KEY AUTOINCREMENT,

                transaction_guid TEXT NOT NULL UNIQUE,

                plan_id INTEGER NOT NULL,
                plan_detail_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,

                qty REAL,
                old_qty_audit REAL,
                new_qty_audit REAL NOT NULL,

                audit_round INTEGER NOT NULL DEFAULT 1,

                audit_staff TEXT,
                audit_user TEXT,
                device_name TEXT,

                is_same_qty INTEGER NOT NULL DEFAULT 0,
                is_confirmed INTEGER NOT NULL DEFAULT 1,

                audit_date TEXT NOT NULL,

                sync_status TEXT NOT NULL DEFAULT 'PENDING',
                sync_attempt INTEGER NOT NULL DEFAULT 0,

                synced_at TEXT,
                sync_error TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY
                (
                    plan_detail_id
                )
                REFERENCES tb_plan_detail
                (
                    plan_detail_id
                )
            )
            """
    )        
    
    # =====================================================
    # create_tb_audit_history
    # =====================================================
    def _create_tb_sync_queue(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Queue กลางสำหรับส่งข้อมูลกลับ Server

        รองรับ:
        - Count
        - Audit
        - Audit ซ้ำ
        - Retry
        - Partial Success
        """

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_sync_queue
            (
                sync_queue_id INTEGER PRIMARY KEY AUTOINCREMENT,

                transaction_guid TEXT NOT NULL UNIQUE,

                plan_id INTEGER NOT NULL,
                plan_detail_id INTEGER,

                sync_type TEXT NOT NULL,

                source_table TEXT NOT NULL,
                source_id INTEGER NOT NULL,

                sync_status TEXT NOT NULL DEFAULT 'PENDING',

                retry_count INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL,
                last_attempt_at TEXT,
                synced_at TEXT,

                error_message TEXT
            )
            """
        )
        
    
    # =====================================================
    # Upgrade Existing Schema
    # =====================================================
    
   
    # =====================================================
    # Add Column If Missing
    # =====================================================
    # =====================================================
    # Column Exists
    # =====================================================
    # =====================================================
    # Validate SQLite Identifier
    # =====================================================
        # =====================================================
    # Ensure SQLite Schema
    # =====================================================
    def _ensure_schema(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        สร้างและปรับปรุงตารางที่ใช้ใน Download Module
        ต้องทำก่อน BEGIN IMMEDIATE เพราะส่วน Schema
        จะ Commit แยกให้เรียบร้อยก่อนเริ่ม Transaction บันทึกข้อมูล
        """
        self._create_tb_plan(connection)
        self._create_tb_item(connection)
        self._create_tb_barcode(connection)
        self._create_tb_location(connection)
        self._create_tb_plan_detail(connection)
        self._create_tb_download_log(connection)

        self._create_tb_audit_history(connection)
        self._create_tb_sync_queue(connection)

        # เพิ่ม Column ให้ฐานข้อมูลเก่า
        self._upgrade_schema(connection)

        # ต้องสร้าง Index หลัง Upgrade
        self._create_indexes(connection)
        connection.commit()
    # =====================================================
    # Table: tb_plan
    # =====================================================
    def _create_tb_plan(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        ข้อมูลหัว Plan ที่ Download มาจาก SQL Server
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_plan
            (
                plan_id INTEGER NOT NULL,
                plan_code TEXT,
                plan_details TEXT,
                plan_check_date TEXT,
                plan_status TEXT,
                udf1 TEXT,
                udf2 TEXT,
                udf3 TEXT,
                create_date TEXT,
                create_by INTEGER,
                update_date TEXT,
                update_by INTEGER,
                is_export INTEGER NOT NULL DEFAULT 0,
                download_date TEXT,
                local_status TEXT NOT NULL DEFAULT 'DOWNLOADED',
                PRIMARY KEY
                (
                    plan_id
                )
            )
            """
        )
    # =====================================================
    # Table: tb_item
    # =====================================================
    def _create_tb_item(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Master Item สำหรับใช้งานบน Android
        item_id คือ Master Item ID
        ที่ Server รวมตาม item_code แล้ว
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_item
            (
                item_id INTEGER NOT NULL,
                item_code TEXT NOT NULL,
                item_name TEXT,
                category TEXT,
                unit_rate REAL NOT NULL DEFAULT 0,
                qty REAL NOT NULL DEFAULT 0,
                uom TEXT,
                unit_cost REAL NOT NULL DEFAULT 0,
                batching_unit TEXT,
                batching_factor REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 0,
                downloaded_at TEXT,
                updated_at TEXT,
                PRIMARY KEY
                (
                    item_id
                )
            )
            """
        )
    # =====================================================
    # Table: tb_barcode
    # =====================================================
    def _create_tb_barcode(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Barcode ทุกตัวของสินค้า
        รวมถึง item_code ที่ Server ส่งมาเป็น Barcode
        เพื่อให้ค้นหาด้วยรหัสสินค้าได้
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_barcode
            (
                barcode_id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                barcode TEXT NOT NULL,
                downloaded_at TEXT,
                FOREIGN KEY
                (
                    item_id
                )
                REFERENCES tb_item
                (
                    item_id
                )
                ON UPDATE CASCADE
                ON DELETE CASCADE,
                UNIQUE
                (
                    item_id,
                    barcode
                )
            )
            """
        )
    # =====================================================
    # Table: tb_location
    # =====================================================
    def _create_tb_location(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Location แยกตาม Plan
        location_id จาก Server เริ่มนับใหม่ในแต่ละ Plan
        จึงใช้ Primary Key แบบ plan_id + location_id
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_location
            (
                plan_id INTEGER NOT NULL,
                location_id INTEGER NOT NULL,
                location_code TEXT NOT NULL,
                location_name TEXT,
                downloaded_at TEXT,
                PRIMARY KEY
                (
                    plan_id,
                    location_id
                ),
                UNIQUE
                (
                    plan_id,
                    location_code
                ),
                FOREIGN KEY
                (
                    plan_id
                )
                REFERENCES tb_plan
                (
                    plan_id
                )
                ON UPDATE CASCADE
                ON DELETE CASCADE
            )
            """
        )
    # =====================================================
    # Table: tb_plan_detail
    # =====================================================
    def _create_tb_plan_detail(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        รายละเอียด Plan
        item_id:
            Master Item ID ที่ Android ใช้ค้นหา
        source_item_id:
            Item ID เดิมจาก SQL Server
            เก็บไว้ใช้ตอน Sync กลับ Server
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_plan_detail
            (
                plan_detail_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                source_item_id INTEGER NOT NULL,
                new_zone TEXT,
                before_zone TEXT,
                new_location TEXT,
                before_location TEXT,
                qty REAL NOT NULL DEFAULT 0,
                qty_on_hand REAL NOT NULL DEFAULT 0,
                qty_audit REAL NOT NULL DEFAULT 0,
                check_date TEXT,
                checker TEXT,
                auditor TEXT,
                status_id INTEGER,
                remark TEXT,
                barcode TEXT,
                udf1 TEXT,
                udf2 TEXT,
                udf3 TEXT,
                audit_count INTEGER NOT NULL DEFAULT 0,
                create_date TEXT,
                create_by INTEGER,
                update_date TEXT,
                update_by INTEGER,
                is_confirm INTEGER NOT NULL DEFAULT 0,
                is_change_location INTEGER NOT NULL DEFAULT 0,
                is_check INTEGER NOT NULL DEFAULT 0,
                local_is_changed INTEGER NOT NULL DEFAULT 0,
                local_sync_status TEXT NOT NULL DEFAULT 'PENDING',
                local_updated_at TEXT,
                PRIMARY KEY
                (
                    plan_detail_id
                ),
                FOREIGN KEY
                (
                    plan_id
                )
                REFERENCES tb_plan
                (
                    plan_id
                )
                ON UPDATE CASCADE
                ON DELETE CASCADE,
                FOREIGN KEY
                (
                    item_id
                )
                REFERENCES tb_item
                (
                    item_id
                )
                ON UPDATE CASCADE
                ON DELETE RESTRICT
            )
            """
        )
    # =====================================================
    # Table: tb_download_log
    # =====================================================
    def _create_tb_download_log(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        เก็บประวัติการ Download ล่าสุดของแต่ละ Plan
        """
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tb_download_log
            (
                download_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                download_date TEXT NOT NULL,
                status TEXT NOT NULL,
                item_count INTEGER NOT NULL DEFAULT 0,
                barcode_count INTEGER NOT NULL DEFAULT 0,
                location_count INTEGER NOT NULL DEFAULT 0,
                detail_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY
                (
                    plan_id
                )
                REFERENCES tb_plan
                (
                    plan_id
                )
                ON UPDATE CASCADE
                ON DELETE CASCADE
            )
            """
        )
    # =====================================================
    # Upgrade Existing Schema
    # =====================================================
    def _upgrade_schema(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        เพิ่ม Column ที่อาจไม่มีใน Database รุ่นเดิม
        SQLite ไม่รองรับ ADD COLUMN หลาย Column พร้อมกัน
        จึงตรวจและเพิ่มทีละ Column
        """
        # -------------------------------------------------
        # tb_plan
        # -------------------------------------------------
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="plan_details",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="plan_check_date",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="plan_status",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="udf1",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="udf2",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="udf3",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="create_date",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="create_by",
            column_definition="INTEGER",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="update_date",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="update_by",
            column_definition="INTEGER",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="is_export",
            column_definition=(
                "INTEGER NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="download_date",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_plan",
            column_name="local_status",
            column_definition=(
                "TEXT NOT NULL DEFAULT 'DOWNLOADED'"
            ),
        )
        # -------------------------------------------------
        # tb_item
        # -------------------------------------------------
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="category",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="unit_rate",
            column_definition=(
                "REAL NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="qty",
            column_definition=(
                "REAL NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="uom",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="unit_cost",
            column_definition=(
                "REAL NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="batching_unit",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="batching_factor",
            column_definition=(
                "REAL NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="is_active",
            column_definition=(
                "INTEGER NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="downloaded_at",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_item",
            column_name="updated_at",
            column_definition="TEXT",
        )
        # -------------------------------------------------
        # tb_barcode
        # -------------------------------------------------
        self._add_column_if_missing(
            connection,
            table_name="tb_barcode",
            column_name="downloaded_at",
            column_definition="TEXT",
        )
        # -------------------------------------------------
        # tb_location
        # -------------------------------------------------
        self._add_column_if_missing(
            connection,
            table_name="tb_location",
            column_name="plan_id",
            column_definition=(
                "INTEGER NOT NULL DEFAULT 0"
            ),
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_location",
            column_name="location_name",
            column_definition="TEXT",
        )
        self._add_column_if_missing(
            connection,
            table_name="tb_location",
            column_name="downloaded_at",
            column_definition="TEXT",
        )
        # -------------------------------------------------
        # tb_plan_detail
        # -------------------------------------------------
        plan_detail_columns = [
            (
                "source_item_id",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "new_zone",
                "TEXT",
            ),
            (
                "before_zone",
                "TEXT",
            ),
            (
                "new_location",
                "TEXT",
            ),
            (
                "before_location",
                "TEXT",
            ),
            (
                "qty",
                "REAL NOT NULL DEFAULT 0",
            ),
            (
                "qty_on_hand",
                "REAL NOT NULL DEFAULT 0",
            ),
            (
                "qty_audit",
                "REAL NOT NULL DEFAULT 0",
            ),
            (
                "check_date",
                "TEXT",
            ),
            (
                "checker",
                "TEXT",
            ),
            (
                "auditor",
                "TEXT",
            ),
            (
                "status_id",
                "INTEGER",
            ),
            (
                "remark",
                "TEXT",
            ),
            (
                "barcode",
                "TEXT",
            ),
            (
                "udf1",
                "TEXT",
            ),
            (
                "udf2",
                "TEXT",
            ),
            (
                "udf3",
                "TEXT",
            ),
            (
                "audit_count",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "create_date",
                "TEXT",
            ),
            (
                "create_by",
                "INTEGER",
            ),
            (
                "update_date",
                "TEXT",
            ),
            (
                "update_by",
                "INTEGER",
            ),
            (
                "is_confirm",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "is_change_location",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "is_check",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "local_is_changed",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "local_sync_status",
                "TEXT NOT NULL DEFAULT 'PENDING'",
            ),
            (
                "local_updated_at",
                "TEXT",
            ),
        ]
        for (
            column_name,
            column_definition,
        ) in plan_detail_columns:
            self._add_column_if_missing(
                connection,
                table_name="tb_plan_detail",
                column_name=column_name,
                column_definition=column_definition,
            )
        # -------------------------------------------------
        # tb_plan_detail: Count / Audit / Server state
        # -------------------------------------------------
        detail_state_columns = [
            ("count_sync_status", "TEXT NOT NULL DEFAULT 'NONE'"),
            ("count_modified_at", "TEXT"),
            ("count_transaction_guid", "TEXT"),
            ("audit_sync_status", "TEXT NOT NULL DEFAULT 'NONE'"),
            ("audit_modified_at", "TEXT"),
            ("audit_transaction_guid", "TEXT"),
            ("audit_user", "TEXT"),
            ("audit_date", "TEXT"),
            ("audit_round", "INTEGER NOT NULL DEFAULT 0"),
            ("server_updated_at", "TEXT"),
            ("downloaded_at", "TEXT"),
        ]
        for column_name, column_definition in detail_state_columns:
            self._add_column_if_missing(
                connection,
                table_name="tb_plan_detail",
                column_name=column_name,
                column_definition=column_definition,
            )

        # -------------------------------------------------
        # tb_audit_history
        # -------------------------------------------------
        audit_history_columns = [
            ("transaction_guid", "TEXT"),
            ("plan_id", "INTEGER"),
            ("plan_detail_id", "INTEGER"),
            ("item_id", "INTEGER"),
            ("qty", "REAL"),
            ("old_qty_audit", "REAL"),
            ("new_qty_audit", "REAL"),
            ("audit_round", "INTEGER NOT NULL DEFAULT 1"),
            ("audit_staff", "TEXT"),
            ("audit_user", "TEXT"),
            ("device_name", "TEXT"),
            ("is_same_qty", "INTEGER NOT NULL DEFAULT 0"),
            ("is_confirmed", "INTEGER NOT NULL DEFAULT 1"),
            ("audit_date", "TEXT"),
            ("sync_status", "TEXT NOT NULL DEFAULT 'PENDING'"),
            ("sync_attempt", "INTEGER NOT NULL DEFAULT 0"),
            ("synced_at", "TEXT"),
            ("sync_error", "TEXT"),
            ("created_at", "TEXT"),
        ]
        for column_name, column_definition in audit_history_columns:
            self._add_column_if_missing(
                connection,
                table_name="tb_audit_history",
                column_name=column_name,
                column_definition=column_definition,
            )

        # -------------------------------------------------
        # tb_sync_queue
        # -------------------------------------------------
        sync_queue_columns = [
            ("transaction_guid", "TEXT"),
            ("plan_id", "INTEGER"),
            ("plan_detail_id", "INTEGER"),
            ("sync_type", "TEXT"),
            ("source_table", "TEXT"),
            ("source_id", "INTEGER"),
            ("sync_status", "TEXT NOT NULL DEFAULT 'PENDING'"),
            ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
            ("created_at", "TEXT"),
            ("last_attempt_at", "TEXT"),
            ("synced_at", "TEXT"),
            ("error_message", "TEXT"),
        ]
        for column_name, column_definition in sync_queue_columns:
            self._add_column_if_missing(
                connection,
                table_name="tb_sync_queue",
                column_name=column_name,
                column_definition=column_definition,
            )

        # -------------------------------------------------
        # tb_download_log
        # -------------------------------------------------
        download_log_columns = [
            (
                "item_count",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "barcode_count",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "location_count",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "detail_count",
                "INTEGER NOT NULL DEFAULT 0",
            ),
            (
                "error_message",
                "TEXT",
            ),
        ]
        for (
            column_name,
            column_definition,
        ) in download_log_columns:
            self._add_column_if_missing(
                connection,
                table_name="tb_download_log",
                column_name=column_name,
                column_definition=column_definition,
            )
    # =====================================================
    # Create Indexes
    # =====================================================
    def _create_indexes(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        """
        Index สำหรับ Download, Count, Audit และ Sync
        """

        # =================================================
        # Item
        # =================================================

        connection.execute(
            """
            DROP INDEX IF EXISTS ux_tb_item_item_code
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_item_item_code
            ON tb_item
            (
                item_code
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_item_item_name
            ON tb_item
            (
                item_name
            )
            """
        )

        # =================================================
        # Barcode
        # =================================================

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_barcode_barcode
            ON tb_barcode
            (
                barcode
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_barcode_item_id
            ON tb_barcode
            (
                item_id
            )
            """
        )

        # =================================================
        # Location
        # =================================================

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_location_plan_code
            ON tb_location
            (
                plan_id,
                location_code
            )
            """
        )

        # =================================================
        # Plan Detail
        # =================================================

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_plan_id
            ON tb_plan_detail
            (
                plan_id
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_plan_item
            ON tb_plan_detail
            (
                plan_id,
                item_id
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_source_item
            ON tb_plan_detail
            (
                source_item_id
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_before_location
            ON tb_plan_detail
            (
                plan_id,
                before_location
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_new_location
            ON tb_plan_detail
            (
                plan_id,
                new_location
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_sync_status
            ON tb_plan_detail
            (
                plan_id,
                local_sync_status
            )
            """
        )

        # =================================================
        # Download Log
        # =================================================

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_download_log_plan
            ON tb_download_log
            (
                plan_id,
                download_date
            )
            """
        )

        # =================================================
        # Count / Audit / Sync
        # =================================================
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_count_sync
            ON tb_plan_detail (plan_id, count_sync_status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_audit_sync
            ON tb_plan_detail (plan_id, audit_sync_status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_audit_history_plan
            ON tb_audit_history (plan_id, audit_date)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_audit_history_detail
            ON tb_audit_history (plan_detail_id, audit_date)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_sync_queue_plan_status
            ON tb_sync_queue (plan_id, sync_status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_tb_sync_queue_type_status
            ON tb_sync_queue (sync_type, sync_status)
            """
        )
    # =====================================================
    # Add Column If Missing
    # =====================================================
    def _add_column_if_missing(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        """
        เพิ่ม Column ให้ Database รุ่นเดิม
        โดยตรวจสอบก่อนว่า Column มีอยู่แล้วหรือไม่
        """
        if self._column_exists(
            connection,
            table_name,
            column_name,
        ):
            return
        safe_table_name = self._validate_identifier(
            table_name
        )
        safe_column_name = self._validate_identifier(
            column_name
        )
        connection.execute(
            f"""
            ALTER TABLE {safe_table_name}
            ADD COLUMN {safe_column_name}
            {column_definition}
            """
        )
    # =====================================================
    # Column Exists
    # =====================================================
    # =====================================================
    # Validate SQLite Identifier
    # =====================================================
    def _validate_identifier(
        self,
        value: str,
    ) -> str:
        """
        ป้องกันการนำ Table หรือ Column Name
        ที่มีอักขระไม่ถูกต้องไปสร้าง Dynamic SQL
        """
        value = str(
            value or ""
        ).strip()
        if not value:
            raise DownloadRepositoryError(
                "SQLite identifier ว่าง"
            )
        if not value.replace(
            "_",
            "",
        ).isalnum():
            raise DownloadRepositoryError(
                f"SQLite identifier ไม่ถูกต้อง: {value}"
            )
        return value
    
    
    def _column_exists(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
    ) -> bool:
        """ตรวจสอบว่า SQLite table มี column ที่ระบุหรือไม่"""
        if not self._table_exists(connection, table_name):
            return False

        safe_table_name = self._validate_identifier(table_name)
        rows = connection.execute(
            f"PRAGMA table_info({safe_table_name})"
        ).fetchall()

        expected = str(column_name or "").strip().lower()
        for row in rows:
            existing = row["name"] if isinstance(row, sqlite3.Row) else row[1]
            if str(existing or "").strip().lower() == expected:
                return True
        return False
            
    # =====================================================
    # Delete Existing Plan Data
    # =====================================================
    def _delete_existing_plan(
        self,
        connection: sqlite3.Connection,
        plan_id: int,
    ) -> None:
        """
        ลบข้อมูลเดิมของ Plan สำหรับ INITIAL DOWNLOAD เท่านั้น

        ต้องเรียก _validate_initial_download_allowed()
        ก่อนเรียก Method นี้เสมอ

        ลำดับการลบต้องเริ่มจาก Child Table
        เพื่อป้องกัน Foreign Key Error
        """

        plan_id = self._to_int(
            plan_id
        )

        if plan_id <= 0:
            raise DownloadRepositoryError(
                "Plan ID สำหรับลบข้อมูลเดิมไม่ถูกต้อง"
            )

        # =====================================================
        # 1. Sync Queue
        # =====================================================

        if self._column_exists(
            connection,
            "tb_sync_queue",
            "plan_id",
        ):
            connection.execute(
                """
                DELETE FROM tb_sync_queue
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            )

        # =====================================================
        # 2. Audit History
        # =====================================================

        if self._column_exists(
            connection,
            "tb_audit_history",
            "plan_id",
        ):
            connection.execute(
                """
                DELETE FROM tb_audit_history
                WHERE plan_id = ?
                """,
                (
                    plan_id,
                ),
            )

        # =====================================================
        # 3. Download Log
        # =====================================================

        connection.execute(
            """
            DELETE FROM tb_download_log
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        )

        # =====================================================
        # 4. Plan Detail
        # =====================================================

        connection.execute(
            """
            DELETE FROM tb_plan_detail
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        )

        # =====================================================
        # 5. Location
        # =====================================================

        connection.execute(
            """
            DELETE FROM tb_location
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        )

        # =====================================================
        # 6. Plan Header
        # =====================================================

        connection.execute(
            """
            DELETE FROM tb_plan
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        )
        
    
    # =====================================================
    # Save Plan
    # =====================================================
    def _save_plan(
        self,
        connection: sqlite3.Connection,
        plan: Dict[str, Any],
    ) -> None:
        """
        บันทึกข้อมูลหัว Plan
        """
        plan_id = self._to_int(
            plan.get("plan_id")
        )
        if plan_id <= 0:
            raise DownloadRepositoryError(
                "ไม่สามารถบันทึก Plan ได้ เนื่องจาก plan_id ไม่ถูกต้อง"
            )
        now_text = self._now_text()
        connection.execute(
            """
            INSERT INTO tb_plan
            (
                plan_id,
                plan_code,
                plan_details,
                plan_check_date,
                plan_status,
                udf1,
                udf2,
                udf3,
                create_date,
                create_by,
                update_date,
                update_by,
                is_export,
                download_date,
                local_status
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            (
                plan_id,
                self._to_text(
                    plan.get("plan_code")
                ),
                self._to_text(
                    plan.get("plan_details")
                ),
                self._to_datetime_text(
                    plan.get("plan_check_date")
                ),
                self._to_text(
                    plan.get("plan_status")
                ),
                self._to_text(
                    plan.get("udf1")
                ),
                self._to_text(
                    plan.get("udf2")
                ),
                self._to_text(
                    plan.get("udf3")
                ),
                self._to_datetime_text(
                    plan.get("create_date")
                ),
                self._to_nullable_int(
                    plan.get("create_by")
                ),
                self._to_datetime_text(
                    plan.get("update_date")
                ),
                self._to_nullable_int(
                    plan.get("update_by")
                ),
                self._to_flag(
                    plan.get("is_export")
                ),
                now_text,
                "DOWNLOADED",
            ),
        )
    # =====================================================
    # Save Items
    # =====================================================
    def _save_items(
        self,
        connection: sqlite3.Connection,
        items: List[Dict[str, Any]],
    ) -> None:
        """
        บันทึก Master Item
        ใช้ item_id เป็น Key หลัก
        หาก item_id เดิมมีอยู่แล้ว จะ Update ข้อมูลล่าสุด
        """
        if not items:
            raise DownloadRepositoryError(
                "ไม่พบข้อมูลสินค้าให้บันทึก"
            )
        now_text = self._now_text()
        rows = []
        for index, item in enumerate(
            items,
            start=1,
        ):
            item_id = self._to_int(
                item.get("item_id")
            )
            item_code = self._to_text(
                item.get("item_code")
            )
            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"สินค้าแถวที่ {index:,} มี item_id ไม่ถูกต้อง"
                )
            if not item_code:
                raise DownloadRepositoryError(
                    f"สินค้าแถวที่ {index:,} ไม่มี item_code"
                )
            rows.append(
                (
                    item_id,
                    item_code,
                    self._to_text(
                        item.get("item_name")
                    ),
                    self._to_text(
                        item.get("category")
                    ),
                    self._to_float(
                        item.get("unit_rate")
                    ),
                    self._to_float(
                        item.get("qty")
                    ),
                    self._to_text(
                        item.get("uom")
                    ),
                    self._to_float(
                        item.get("unit_cost")
                    ),
                    self._to_text(
                        item.get("batching_unit")
                    ),
                    self._to_float(
                        item.get("batching_factor")
                    ),
                    self._to_flag(
                        item.get("is_active")
                    ),
                    now_text,
                    now_text,
                )
            )
        connection.executemany(
            """
            INSERT INTO tb_item
            (
                item_id,
                item_code,
                item_name,
                category,
                unit_rate,
                qty,
                uom,
                unit_cost,
                batching_unit,
                batching_factor,
                is_active,
                downloaded_at,
                updated_at
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
            ON CONFLICT(item_id)
            DO UPDATE SET
                item_code = excluded.item_code,
                item_name = excluded.item_name,
                category = excluded.category,
                unit_rate = excluded.unit_rate,
                qty = excluded.qty,
                uom = excluded.uom,
                unit_cost = excluded.unit_cost,
                batching_unit = excluded.batching_unit,
                batching_factor = excluded.batching_factor,
                is_active = excluded.is_active,
                downloaded_at = excluded.downloaded_at,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    # =====================================================
    # Save Barcodes
    # =====================================================
        # =====================================================
    # Save Barcodes
    # =====================================================

    def _save_barcodes(
        self,
        connection: sqlite3.Connection,
        barcodes: List[Dict[str, Any]],
    ) -> None:
        """
        บันทึก Barcode โดยรองรับฐานข้อมูล SQLite รุ่นเดิม
        ที่อาจไม่มี UNIQUE(item_id, barcode)
        """

        if not barcodes:
            return

        now_text = self._now_text()

        rows = []
        unique_keys = set()

        for index, barcode_row in enumerate(
            barcodes,
            start=1,
        ):
            item_id = self._to_int(
                barcode_row.get("item_id")
            )

            barcode = self._to_text(
                barcode_row.get("barcode")
            )

            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"Barcode แถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )

            if not barcode:
                continue

            key = (
                item_id,
                barcode,
            )

            if key in unique_keys:
                continue

            unique_keys.add(key)

            rows.append(
                (
                    item_id,
                    barcode,
                    now_text,
                )
            )

        if not rows:
            return

        # ลบ Barcode เดิมก่อน เพื่อไม่ให้ข้อมูลซ้ำ
        connection.executemany(
            """
            DELETE FROM tb_barcode
            WHERE item_id = ?
              AND barcode = ?
            """,
            [
                (
                    row[0],
                    row[1],
                )
                for row in rows
            ],
        )

        # Insert ใหม่โดยไม่ใช้ ON CONFLICT
        connection.executemany(
            """
            INSERT INTO tb_barcode
            (
                item_id,
                barcode,
                downloaded_at
            )
            VALUES
            (
                ?,
                ?,
                ?
            )
            """,
            rows,
        )
    # =====================================================
    # Save Locations
    # =====================================================
        # =====================================================
    # Save Locations
    # =====================================================

    def _save_locations(
        self,
        connection: sqlite3.Connection,
        locations: List[Dict[str, Any]],
    ) -> None:
        """
        บันทึก Location โดยรองรับฐานข้อมูล SQLite รุ่นเดิม
        ที่อาจไม่มี PRIMARY KEY(plan_id, location_id)
        """

        if not locations:
            return

        now_text = self._now_text()

        rows = []
        unique_keys = set()

        for index, location in enumerate(
            locations,
            start=1,
        ):
            plan_id = self._to_int(
                location.get("plan_id")
            )

            location_id = self._to_int(
                location.get("location_id")
            )

            location_code = self._to_text(
                location.get("location_code")
            )

            if plan_id <= 0:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "มี plan_id ไม่ถูกต้อง"
                )

            if location_id <= 0:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "มี location_id ไม่ถูกต้อง"
                )

            if not location_code:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "ไม่มี location_code"
                )

            key = (
                plan_id,
                location_id,
            )

            if key in unique_keys:
                continue

            unique_keys.add(key)

            rows.append(
                (
                    plan_id,
                    location_id,
                    location_code,
                    self._to_text(
                        location.get("location_name")
                    ),
                    now_text,
                )
            )

        if not rows:
            return

        # ลบ Location เดิมก่อน
        connection.executemany(
            """
            DELETE FROM tb_location
            WHERE plan_id = ?
              AND location_id = ?
            """,
            [
                (
                    row[0],
                    row[1],
                )
                for row in rows
            ],
        )

        # Insert ใหม่โดยไม่ใช้ ON CONFLICT
        connection.executemany(
            """
            INSERT INTO tb_location
            (
                plan_id,
                location_id,
                location_code,
                location_name,
                downloaded_at
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?
            )
            """,
            rows,
        )
    # =====================================================
    # Save Plan Details
    # =====================================================
    def _save_details(
        self,
        connection: sqlite3.Connection,
        details: List[Dict[str, Any]],
    ) -> None:
        """
        บันทึกรายละเอียดสินค้าใน Plan สำหรับ INITIAL DOWNLOAD

        กติกา:
        - ข้อมูลมาจาก Server
        - ยังไม่มี Local Change
        - ยังไม่มีข้อมูลรอ Sync
        - qty, qty_on_hand และ qty_audit รับค่าจาก Server
        """

        if not details:
            raise DownloadRepositoryError(
                "ไม่พบรายละเอียด Plan ให้บันทึก"
            )

        downloaded_at = self._now_text()
        rows = []

        for index, detail in enumerate(
            details,
            start=1,
        ):
            plan_detail_id = self._to_int(
                detail.get("plan_detail_id")
            )

            plan_id = self._to_int(
                detail.get("plan_id")
            )

            item_id = self._to_int(
                detail.get("item_id")
            )

            source_item_id = self._to_int(
                detail.get("source_item_id")
            )

            if plan_detail_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี plan_detail_id ไม่ถูกต้อง"
                )

            if plan_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี plan_id ไม่ถูกต้อง"
                )

            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )

            if source_item_id <= 0:
                source_item_id = item_id

            server_update_date = self._to_datetime_text(
                detail.get("update_date")
            )

            audit_count = self._to_int(
                detail.get("audit_count")
            )

            rows.append(
                {
                    "plan_detail_id": plan_detail_id,
                    "plan_id": plan_id,
                    "item_id": item_id,
                    "source_item_id": source_item_id,

                    "new_zone": self._to_text(
                        detail.get("new_zone")
                    ),
                    "before_zone": self._to_text(
                        detail.get("before_zone")
                    ),
                    "new_location": self._to_text(
                        detail.get("new_location")
                    ),
                    "before_location": self._to_text(
                        detail.get("before_location")
                    ),

                    "qty": self._to_float(
                        detail.get("qty")
                    ),
                    "qty_on_hand": self._to_float(
                        detail.get("qty_on_hand")
                    ),
                    "qty_audit": self._to_float(
                        detail.get("qty_audit")
                    ),

                    "check_date": self._to_datetime_text(
                        detail.get("check_date")
                    ),
                    "checker": self._to_text(
                        detail.get("checker")
                    ),
                    "auditor": self._to_text(
                        detail.get("auditor")
                    ),

                    "status_id": self._to_nullable_int(
                        detail.get("status_id")
                    ),
                    "remark": self._to_text(
                        detail.get("remark")
                    ),
                    "barcode": self._to_text(
                        detail.get("barcode")
                    ),

                    "udf1": self._to_text(
                        detail.get("udf1")
                    ),
                    "udf2": self._to_text(
                        detail.get("udf2")
                    ),
                    "udf3": self._to_text(
                        detail.get("udf3")
                    ),

                    "audit_count": audit_count,

                    "create_date": self._to_datetime_text(
                        detail.get("create_date")
                    ),
                    "create_by": self._to_nullable_int(
                        detail.get("create_by")
                    ),
                    "update_date": server_update_date,
                    "update_by": self._to_nullable_int(
                        detail.get("update_by")
                    ),

                    "is_confirm": self._to_flag(
                        detail.get("is_confirm")
                    ),
                    "is_change_location": self._to_flag(
                        detail.get("is_change_location")
                    ),
                    "is_check": self._to_flag(
                        detail.get("is_check")
                    ),

                    # Legacy Local State
                    "local_is_changed": 0,
                    "local_sync_status": "NONE",
                    "local_updated_at": None,

                    # Count Local State
                    "count_sync_status": "NONE",
                    "count_modified_at": None,
                    "count_transaction_guid": None,

                    # Audit Local State
                    "audit_sync_status": "NONE",
                    "audit_modified_at": None,
                    "audit_transaction_guid": None,

                    # Current Audit State
                    "audit_user": None,
                    "audit_date": self._to_datetime_text(
                        detail.get("check_date")
                    ),
                    "audit_round": max(1, self._to_int(detail.get("audit_round")) or (audit_count + 1)),

                    # Server State
                    "server_updated_at": server_update_date,
                    "downloaded_at": downloaded_at,
                }
            )

        connection.executemany(
            """
            INSERT INTO tb_plan_detail
            (
                plan_detail_id,
                plan_id,
                item_id,
                source_item_id,

                new_zone,
                before_zone,
                new_location,
                before_location,

                qty,
                qty_on_hand,
                qty_audit,

                check_date,
                checker,
                auditor,

                status_id,
                remark,
                barcode,

                udf1,
                udf2,
                udf3,

                audit_count,

                create_date,
                create_by,
                update_date,
                update_by,

                is_confirm,
                is_change_location,
                is_check,

                local_is_changed,
                local_sync_status,
                local_updated_at,

                count_sync_status,
                count_modified_at,
                count_transaction_guid,

                audit_sync_status,
                audit_modified_at,
                audit_transaction_guid,

                audit_user,
                audit_date,
                audit_round,

                server_updated_at,
                downloaded_at
            )
            VALUES
            (
                :plan_detail_id,
                :plan_id,
                :item_id,
                :source_item_id,

                :new_zone,
                :before_zone,
                :new_location,
                :before_location,

                :qty,
                :qty_on_hand,
                :qty_audit,

                :check_date,
                :checker,
                :auditor,

                :status_id,
                :remark,
                :barcode,

                :udf1,
                :udf2,
                :udf3,

                :audit_count,

                :create_date,
                :create_by,
                :update_date,
                :update_by,

                :is_confirm,
                :is_change_location,
                :is_check,

                :local_is_changed,
                :local_sync_status,
                :local_updated_at,

                :count_sync_status,
                :count_modified_at,
                :count_transaction_guid,

                :audit_sync_status,
                :audit_modified_at,
                :audit_transaction_guid,

                :audit_user,
                :audit_date,
                :audit_round,

                :server_updated_at,
                :downloaded_at
            )
            """,
            rows,
        )
        
    def _refresh_details(
        self,
        connection: sqlite3.Connection,
        details: List[Dict[str, Any]],
    ) -> None:
        """
        Refresh Plan Detail จาก Server

        กติกา:
        - plan_detail_id เดิม ให้ Update
        - plan_detail_id ใหม่ ให้ Insert
        - qty รับค่าจาก Server เสมอ
        - qty_on_hand ห้ามทับเมื่อ Count ยังรอ Sync
        - qty_audit ห้ามทับเมื่อ Audit ยังรอ Sync
        - Local transaction และ Local user ต้องไม่ถูกล้าง
        """

        if not details:
            raise DownloadRepositoryError(
                "ไม่พบรายละเอียด Plan สำหรับ Refresh"
            )

        downloaded_at = self._now_text()
        rows = []

        for index, detail in enumerate(
            details,
            start=1,
        ):
            plan_detail_id = self._to_int(
                detail.get("plan_detail_id")
            )

            plan_id = self._to_int(
                detail.get("plan_id")
            )

            item_id = self._to_int(
                detail.get("item_id")
            )

            source_item_id = self._to_int(
                detail.get("source_item_id")
            )

            if plan_detail_id <= 0:
                raise DownloadRepositoryError(
                    f"Refresh Detail แถวที่ {index:,} "
                    "มี plan_detail_id ไม่ถูกต้อง"
                )

            if plan_id <= 0:
                raise DownloadRepositoryError(
                    f"Refresh Detail แถวที่ {index:,} "
                    "มี plan_id ไม่ถูกต้อง"
                )

            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"Refresh Detail แถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )

            if source_item_id <= 0:
                source_item_id = item_id

            server_update_date = self._to_datetime_text(
                detail.get("update_date")
            )

            audit_count = self._to_int(
                detail.get("audit_count")
            )

            rows.append(
                {
                    "plan_detail_id": plan_detail_id,
                    "plan_id": plan_id,
                    "item_id": item_id,
                    "source_item_id": source_item_id,

                    "new_zone": self._to_text(
                        detail.get("new_zone")
                    ),
                    "before_zone": self._to_text(
                        detail.get("before_zone")
                    ),
                    "new_location": self._to_text(
                        detail.get("new_location")
                    ),
                    "before_location": self._to_text(
                        detail.get("before_location")
                    ),

                    "qty": self._to_float(
                        detail.get("qty")
                    ),
                    "qty_on_hand": self._to_float(
                        detail.get("qty_on_hand")
                    ),
                    "qty_audit": self._to_float(
                        detail.get("qty_audit")
                    ),

                    "check_date": self._to_datetime_text(
                        detail.get("check_date")
                    ),
                    "checker": self._to_text(
                        detail.get("checker")
                    ),
                    "auditor": self._to_text(
                        detail.get("auditor")
                    ),

                    "status_id": self._to_nullable_int(
                        detail.get("status_id")
                    ),
                    "remark": self._to_text(
                        detail.get("remark")
                    ),
                    "barcode": self._to_text(
                        detail.get("barcode")
                    ),

                    "udf1": self._to_text(
                        detail.get("udf1")
                    ),
                    "udf2": self._to_text(
                        detail.get("udf2")
                    ),
                    "udf3": self._to_text(
                        detail.get("udf3")
                    ),

                    "audit_count": audit_count,

                    "create_date": self._to_datetime_text(
                        detail.get("create_date")
                    ),
                    "create_by": self._to_nullable_int(
                        detail.get("create_by")
                    ),
                    "update_date": server_update_date,
                    "update_by": self._to_nullable_int(
                        detail.get("update_by")
                    ),

                    "is_confirm": self._to_flag(
                        detail.get("is_confirm")
                    ),
                    "is_change_location": self._to_flag(
                        detail.get("is_change_location")
                    ),
                    "is_check": self._to_flag(
                        detail.get("is_check")
                    ),

                    "audit_date": self._to_datetime_text(
                        detail.get("check_date")
                    ),
                    "audit_round": max(1, self._to_int(detail.get("audit_round")) or (audit_count + 1)),

                    "server_updated_at": server_update_date,
                    "downloaded_at": downloaded_at,
                }
            )

        connection.executemany(
            """
            INSERT INTO tb_plan_detail
            (
                plan_detail_id,
                plan_id,
                item_id,
                source_item_id,

                new_zone,
                before_zone,
                new_location,
                before_location,

                qty,
                qty_on_hand,
                qty_audit,

                check_date,
                checker,
                auditor,

                status_id,
                remark,
                barcode,

                udf1,
                udf2,
                udf3,

                audit_count,

                create_date,
                create_by,
                update_date,
                update_by,

                is_confirm,
                is_change_location,
                is_check,

                local_is_changed,
                local_sync_status,
                local_updated_at,

                count_sync_status,
                count_modified_at,
                count_transaction_guid,

                audit_sync_status,
                audit_modified_at,
                audit_transaction_guid,

                audit_user,
                audit_date,
                audit_round,

                server_updated_at,
                downloaded_at
            )
            VALUES
            (
                :plan_detail_id,
                :plan_id,
                :item_id,
                :source_item_id,

                :new_zone,
                :before_zone,
                :new_location,
                :before_location,

                :qty,
                :qty_on_hand,
                :qty_audit,

                :check_date,
                :checker,
                :auditor,

                :status_id,
                :remark,
                :barcode,

                :udf1,
                :udf2,
                :udf3,

                :audit_count,

                :create_date,
                :create_by,
                :update_date,
                :update_by,

                :is_confirm,
                :is_change_location,
                :is_check,

                0,
                'NONE',
                NULL,

                'NONE',
                NULL,
                NULL,

                'NONE',
                NULL,
                NULL,

                NULL,
                :audit_date,
                :audit_round,

                :server_updated_at,
                :downloaded_at
            )

            ON CONFLICT(plan_detail_id)
            DO UPDATE SET

                plan_id = excluded.plan_id,
                item_id = excluded.item_id,
                source_item_id = excluded.source_item_id,

                new_zone = excluded.new_zone,
                before_zone = excluded.before_zone,
                new_location = excluded.new_location,
                before_location = excluded.before_location,

                /*
                qty คือค่าที่ Server ประมวลผลล่าสุด
                จึงรับจาก Server ทุกครั้ง
                */
                qty = excluded.qty,

                /*
                หาก Count ยังมี Local Pending/Error/Syncing
                ให้รักษา qty_on_hand ในเครื่อง
                */
                qty_on_hand =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.count_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.qty_on_hand

                        ELSE excluded.qty_on_hand
                    END,

                /*
                หาก Audit ยังมี Local Pending/Error/Syncing
                ให้รักษา qty_audit ล่าสุดในเครื่อง
                */
                qty_audit =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.qty_audit

                        ELSE excluded.qty_audit
                    END,

                check_date =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.count_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.check_date

                        ELSE excluded.check_date
                    END,

                checker =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.count_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.checker

                        ELSE excluded.checker
                    END,

                /*
                auditor คือ Staff เจ้าของงาน Audit
                หากมี Audit Local ค้างอยู่ ห้ามเปลี่ยน
                */
                auditor =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.auditor

                        ELSE excluded.auditor
                    END,

                status_id = excluded.status_id,
                remark = excluded.remark,
                barcode = excluded.barcode,

                udf1 = excluded.udf1,
                udf2 = excluded.udf2,
                udf3 = excluded.udf3,

                audit_count =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.audit_count

                        ELSE excluded.audit_count
                    END,

                create_date = excluded.create_date,
                create_by = excluded.create_by,
                update_date = excluded.update_date,
                update_by = excluded.update_by,

                is_confirm = excluded.is_confirm,
                is_change_location = excluded.is_change_location,
                is_check = excluded.is_check,

                /*
                Local State ไม่ถูกแก้ใน Refresh
                */
                local_is_changed =
                    tb_plan_detail.local_is_changed,

                local_sync_status =
                    tb_plan_detail.local_sync_status,

                local_updated_at =
                    tb_plan_detail.local_updated_at,

                count_sync_status =
                    tb_plan_detail.count_sync_status,

                count_modified_at =
                    tb_plan_detail.count_modified_at,

                count_transaction_guid =
                    tb_plan_detail.count_transaction_guid,

                audit_sync_status =
                    tb_plan_detail.audit_sync_status,

                audit_modified_at =
                    tb_plan_detail.audit_modified_at,

                audit_transaction_guid =
                    tb_plan_detail.audit_transaction_guid,

                audit_user =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.audit_user

                        ELSE NULL
                    END,

                audit_date =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.audit_date

                        ELSE excluded.audit_date
                    END,

                audit_round =
                    CASE
                        WHEN UPPER(
                            COALESCE(
                                tb_plan_detail.audit_sync_status,
                                'NONE'
                            )
                        ) IN
                        (
                            'PENDING',
                            'SYNCING',
                            'ERROR'
                        )
                        THEN tb_plan_detail.audit_round

                        ELSE excluded.audit_round
                    END,

                server_updated_at =
                    excluded.server_updated_at,

                downloaded_at =
                    excluded.downloaded_at
            """,
            rows,
        )    
        
    # =====================================================
    # Save Download Metadata
    # =====================================================
    def _save_download_metadata(
        self,
        connection: sqlite3.Connection,
        plan_id: int,
    ) -> None:
        """
        บันทึก Log จำนวนข้อมูลที่บันทึกจริงใน SQLite
        """
        plan_id = self._to_int(
            plan_id
        )
        if plan_id <= 0:
            raise DownloadRepositoryError(
                "Plan ID สำหรับบันทึก Download Log ไม่ถูกต้อง"
            )
        item_count_row = connection.execute(
            """
            SELECT COUNT(DISTINCT item_id)
            FROM tb_plan_detail
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        ).fetchone()
        barcode_count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM tb_barcode b
            WHERE EXISTS
            (
                SELECT 1
                FROM tb_plan_detail d
                WHERE d.plan_id = ?
                  AND d.item_id = b.item_id
            )
            """,
            (
                plan_id,
            ),
        ).fetchone()
        location_count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM tb_location
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        ).fetchone()
        detail_count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM tb_plan_detail
            WHERE plan_id = ?
            """,
            (
                plan_id,
            ),
        ).fetchone()
        item_count = self._row_count(
            item_count_row
        )
        barcode_count = self._row_count(
            barcode_count_row
        )
        location_count = self._row_count(
            location_count_row
        )
        detail_count = self._row_count(
            detail_count_row
        )
        connection.execute(
            """
            INSERT INTO tb_download_log
            (
                plan_id,
                download_date,
                status,
                item_count,
                barcode_count,
                location_count,
                detail_count,
                error_message
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                NULL
            )
            """,
            (
                plan_id,
                self._now_text(),
                "SAVED",
                item_count,
                barcode_count,
                location_count,
                detail_count,
            ),
        )
        # =====================================================
    # Validate Package
    # =====================================================
    def _validate_package(
        self,
        package: Dict[str, Any],
    ) -> None:
        """
        ตรวจสอบโครงสร้างข้อมูลที่ได้รับจาก DownloadPlan.ashx
        ก่อนเริ่มบันทึกลง SQLite
        """
        if not isinstance(
            package,
            dict,
        ):
            raise DownloadRepositoryError(
                "Download Package ต้องเป็น dict"
            )
        required_keys = (
            "plan",
            "items",
            "barcodes",
            "locations",
            "details",
        )
        missing_keys = [
            key
            for key in required_keys
            if key not in package
        ]
        if missing_keys:
            raise DownloadRepositoryError(
                "Download Package ขาดข้อมูล: "
                + ", ".join(missing_keys)
            )
        plan = package.get("plan")
        items = package.get("items")
        barcodes = package.get("barcodes")
        locations = package.get("locations")
        details = package.get("details")
        if not isinstance(
            plan,
            dict,
        ):
            raise DownloadRepositoryError(
                "ข้อมูล plan ต้องเป็น dict"
            )
        list_fields = (
            (
                "items",
                items,
            ),
            (
                "barcodes",
                barcodes,
            ),
            (
                "locations",
                locations,
            ),
            (
                "details",
                details,
            ),
        )
        for field_name, field_value in list_fields:
            if not isinstance(
                field_value,
                list,
            ):
                raise DownloadRepositoryError(
                    f"ข้อมูล {field_name} ต้องเป็น list"
                )
        self._validate_plan(
            plan
        )
        self._validate_items(
            items
        )
        self._validate_barcodes(
            barcodes
        )
        self._validate_locations(
            locations,
            expected_plan_id=self._to_int(
                plan.get("plan_id")
            ),
        )
        self._validate_details(
            details,
            expected_plan_id=self._to_int(
                plan.get("plan_id")
            ),
            items=items,
        )
    # =====================================================
    # Validate Plan
    # =====================================================
    def _validate_plan(
        self,
        plan: Dict[str, Any],
    ) -> None:
        """
        ตรวจสอบข้อมูลหัว Plan
        """
        plan_id = self._to_int(
            plan.get("plan_id")
        )
        if plan_id <= 0:
            raise DownloadRepositoryError(
                "plan.plan_id ไม่ถูกต้อง"
            )
        plan_code = self._to_text(
            plan.get("plan_code")
        )
        if not plan_code:
            raise DownloadRepositoryError(
                "plan.plan_code ว่าง"
            )
        if len(plan_code) > 100:
            raise DownloadRepositoryError(
                "plan.plan_code ยาวเกิน 100 ตัวอักษร"
            )
    # =====================================================
    # Validate Items
    # =====================================================
    def _validate_items(
        self,
        items: List[Dict[str, Any]],
    ) -> None:
        """
        ตรวจสอบ Master Item
        เงื่อนไขหลัก:
            - ต้องมีอย่างน้อย 1 รายการ
            - item_id ต้องไม่ซ้ำ
            - item_code ต้องไม่ซ้ำ
        """
        if not items:
            raise DownloadRepositoryError(
                "ไม่พบข้อมูลสินค้าใน Download Package"
            )
        item_ids = set()
        item_codes = set()
        for index, item in enumerate(
            items,
            start=1,
        ):
            if not isinstance(
                item,
                dict,
            ):
                raise DownloadRepositoryError(
                    f"สินค้าแถวที่ {index:,} ต้องเป็น dict"
                )
            item_id = self._to_int(
                item.get("item_id")
            )
            item_code = self._to_text(
                item.get("item_code")
            )
            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"สินค้าแถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )
            if not item_code:
                raise DownloadRepositoryError(
                    f"สินค้าแถวที่ {index:,} "
                    "ไม่มี item_code"
                )
            normalized_item_code = (
                item_code.strip().upper()
            )
            if item_id in item_ids:
                raise DownloadRepositoryError(
                    f"พบ item_id ซ้ำ: {item_id}"
                )
            if normalized_item_code in item_codes:
                raise DownloadRepositoryError(
                    f"พบ item_code ซ้ำ: {item_code}"
                )
            item_ids.add(
                item_id
            )
            item_codes.add(
                normalized_item_code
            )
    # =====================================================
    # Validate Barcodes
    # =====================================================
    def _validate_barcodes(
        self,
        barcodes: List[Dict[str, Any]],
    ) -> None:
        """
        ตรวจสอบ Barcode
        Barcode ว่างจะถูกข้ามตอนบันทึก
        แต่ item_id ต้องถูกต้อง
        """
        unique_pairs = set()
        for index, barcode_row in enumerate(
            barcodes,
            start=1,
        ):
            if not isinstance(
                barcode_row,
                dict,
            ):
                raise DownloadRepositoryError(
                    f"Barcode แถวที่ {index:,} ต้องเป็น dict"
                )
            item_id = self._to_int(
                barcode_row.get("item_id")
            )
            barcode = self._to_text(
                barcode_row.get("barcode")
            )
            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"Barcode แถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )
            if not barcode:
                continue
            normalized_barcode = (
                barcode.strip().upper()
            )
            unique_key = (
                item_id,
                normalized_barcode,
            )
            if unique_key in unique_pairs:
                continue
            unique_pairs.add(
                unique_key
            )
    # =====================================================
    # Validate Locations
    # =====================================================
    def _validate_locations(
        self,
        locations: List[Dict[str, Any]],
        expected_plan_id: int,
    ) -> None:
        """
        ตรวจสอบ Location ของ Plan
        """
        location_ids = set()
        location_codes = set()
        for index, location in enumerate(
            locations,
            start=1,
        ):
            if not isinstance(
                location,
                dict,
            ):
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} ต้องเป็น dict"
                )
            plan_id = self._to_int(
                location.get("plan_id")
            )
            location_id = self._to_int(
                location.get("location_id")
            )
            location_code = self._to_text(
                location.get("location_code")
            )
            if plan_id <= 0:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "มี plan_id ไม่ถูกต้อง"
                )
            if (
                expected_plan_id > 0
                and
                plan_id != expected_plan_id
            ):
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    f"อยู่คนละ Plan "
                    f"(พบ {plan_id}, "
                    f"ต้องเป็น {expected_plan_id})"
                )
            if location_id <= 0:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "มี location_id ไม่ถูกต้อง"
                )
            if not location_code:
                raise DownloadRepositoryError(
                    f"Location แถวที่ {index:,} "
                    "ไม่มี location_code"
                )
            location_id_key = (
                plan_id,
                location_id,
            )
            location_code_key = (
                plan_id,
                location_code.strip().upper(),
            )
            if location_id_key in location_ids:
                raise DownloadRepositoryError(
                    "พบ location_id ซ้ำใน Plan: "
                    f"{location_id}"
                )
            if location_code_key in location_codes:
                raise DownloadRepositoryError(
                    "พบ location_code ซ้ำใน Plan: "
                    f"{location_code}"
                )
            location_ids.add(
                location_id_key
            )
            location_codes.add(
                location_code_key
            )
    # =====================================================
    # Validate Details
    # =====================================================
    def _validate_details(
        self,
        details: List[Dict[str, Any]],
        expected_plan_id: int,
        items: List[Dict[str, Any]],
    ) -> None:
        """
        ตรวจสอบรายละเอียด Plan
        ตรวจสอบว่า:
            - plan_detail_id ไม่ซ้ำ
            - plan_id ตรงกับหัว Plan
            - item_id อยู่ใน Master Item
            - source_item_id ถูกต้อง
        """
        if not details:
            raise DownloadRepositoryError(
                "ไม่พบรายละเอียด Plan"
            )
        valid_item_ids = {
            self._to_int(
                item.get("item_id")
            )
            for item in items
            if self._to_int(
                item.get("item_id")
            ) > 0
        }
        plan_detail_ids = set()
        for index, detail in enumerate(
            details,
            start=1,
        ):
            if not isinstance(
                detail,
                dict,
            ):
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} ต้องเป็น dict"
                )
            plan_detail_id = self._to_int(
                detail.get("plan_detail_id")
            )
            plan_id = self._to_int(
                detail.get("plan_id")
            )
            item_id = self._to_int(
                detail.get("item_id")
            )
            source_item_id = self._to_int(
                detail.get("source_item_id")
            )
            if plan_detail_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี plan_detail_id ไม่ถูกต้อง"
                )
            if plan_detail_id in plan_detail_ids:
                raise DownloadRepositoryError(
                    "พบ plan_detail_id ซ้ำ: "
                    f"{plan_detail_id}"
                )
            if plan_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี plan_id ไม่ถูกต้อง"
                )
            if (
                expected_plan_id > 0
                and
                plan_id != expected_plan_id
            ):
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    f"อยู่คนละ Plan "
                    f"(พบ {plan_id}, "
                    f"ต้องเป็น {expected_plan_id})"
                )
            if item_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี item_id ไม่ถูกต้อง"
                )
            if item_id not in valid_item_ids:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    f"อ้างอิง item_id {item_id} "
                    "ที่ไม่มีใน Master Item"
                )
            if source_item_id < 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} "
                    "มี source_item_id ไม่ถูกต้อง"
                )
            plan_detail_ids.add(
                plan_detail_id
            )
        # =====================================================
    # Convert To Integer
    # =====================================================
    def _to_int(
        self,
        value: Any,
        default: int = 0,
    ) -> int:
        """
        แปลงค่าเป็น int
        รองรับ:
            - None
            - int
            - float
            - Decimal
            - string เช่น "10", "10.00"
            - boolean
        """
        if value is None:
            return default
        if isinstance(
            value,
            bool,
        ):
            return 1 if value else 0
        if isinstance(
            value,
            int,
        ):
            return value
        if isinstance(
            value,
            (
                float,
                Decimal,
            ),
        ):
            try:
                return int(
                    value
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                return default
        text = str(
            value
        ).strip()
        if not text:
            return default
        normalized = text.replace(
            ",",
            "",
        )
        try:
            return int(
                normalized
            )
        except ValueError:
            try:
                return int(
                    float(
                        normalized
                    )
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                return default
    # =====================================================
    # Convert To Nullable Integer
    # =====================================================
    def _to_nullable_int(
        self,
        value: Any,
    ) -> Optional[int]:
        """
        แปลงค่าเป็น int
        ถ้าค่าว่างหรือแปลงไม่ได้ จะคืน None
        เหมาะกับ Column ที่อนุญาต NULL
        """
        if value is None:
            return None
        if isinstance(
            value,
            str,
        ):
            text = value.strip()
            if not text:
                return None
            if text.lower() in (
                "none",
                "null",
            ):
                return None
        try:
            if isinstance(
                value,
                bool,
            ):
                return 1 if value else 0
            if isinstance(
                value,
                int,
            ):
                return value
            if isinstance(
                value,
                (
                    float,
                    Decimal,
                ),
            ):
                return int(
                    value
                )
            normalized = str(
                value
            ).strip().replace(
                ",",
                "",
            )
            if not normalized:
                return None
            try:
                return int(
                    normalized
                )
            except ValueError:
                return int(
                    float(
                        normalized
                    )
                )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None
    # =====================================================
    # Convert To Float
    # =====================================================
    def _to_float(
        self,
        value: Any,
        default: float = 0.0,
    ) -> float:
        """
        แปลงค่าเป็น float
        รองรับค่าแบบ:
            1
            1.5
            Decimal
            "1.50"
            "1,250.75"
        """
        if value is None:
            return default
        if isinstance(
            value,
            bool,
        ):
            return 1.0 if value else 0.0
        if isinstance(
            value,
            (
                int,
                float,
                Decimal,
            ),
        ):
            try:
                return float(
                    value
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                return default
        text = str(
            value
        ).strip()
        if not text:
            return default
        normalized = text.replace(
            ",",
            "",
        )
        try:
            return float(
                normalized
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return default
    # =====================================================
    # Convert To Flag
    # =====================================================
    def _to_flag(
        self,
        value: Any,
        default: int = 0,
    ) -> int:
        """
        แปลงค่าหลายรูปแบบเป็น 0 หรือ 1
        True values:
            1
            true
            yes
            y
            on
            active
        False values:
            0
            false
            no
            n
            off
            inactive
        """
        if value is None:
            return 1 if default else 0
        if isinstance(
            value,
            bool,
        ):
            return 1 if value else 0
        if isinstance(
            value,
            (
                int,
                float,
                Decimal,
            ),
        ):
            return 1 if float(value) != 0 else 0
        text = str(
            value
        ).strip().lower()
        if not text:
            return 1 if default else 0
        true_values = {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "active",
            "enabled",
        }
        false_values = {
            "0",
            "false",
            "no",
            "n",
            "off",
            "inactive",
            "disabled",
            "none",
            "null",
        }
        if text in true_values:
            return 1
        if text in false_values:
            return 0
        try:
            return 1 if float(text) != 0 else 0
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return 1 if default else 0
    # =====================================================
    # Convert To Text
    # =====================================================
    def _to_text(
        self,
        value: Any,
        default: str = "",
    ) -> str:
        """
        แปลงค่าเป็นข้อความแบบปลอดภัย
        None จะคืนค่า default
        """
        if value is None:
            return default
        if isinstance(
            value,
            bytes,
        ):
            try:
                return value.decode(
                    "utf-8"
                ).strip()
            except UnicodeDecodeError:
                return value.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
        try:
            return str(
                value
            ).strip()
        except Exception:
            return default
    # =====================================================
    # Convert To DateTime Text
    # =====================================================
    def _to_datetime_text(
        self,
        value: Any,
    ) -> Optional[str]:
        """
        แปลงวันที่เป็นรูปแบบข้อความสำหรับ SQLite
        รูปแบบผลลัพธ์:
            YYYY-MM-DD HH:MM:SS
        ถ้าไม่มีค่า จะคืน None
        """
        if value is None:
            return None
        if isinstance(
            value,
            datetime,
        ):
            return value.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        if isinstance(
            value,
            date,
        ):
            return datetime.combine(
                value,
                datetime.min.time(),
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        text = self._to_text(
            value
        )
        if not text:
            return None
        if text.lower() in (
            "none",
            "null",
        ):
            return None
        normalized = text.strip()
        if normalized.endswith(
            "Z"
        ):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )
        try:
            parsed = datetime.fromisoformat(
                normalized
            )
            return parsed.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            pass
        accepted_formats = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
        )
        for date_format in accepted_formats:
            try:
                parsed = datetime.strptime(
                    normalized,
                    date_format,
                )
                return parsed.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                continue
        # ถ้า Server ส่งรูปแบบที่ Python อ่านไม่ได้
        # ให้เก็บข้อความเดิมไว้ เพื่อไม่ให้ข้อมูลหาย
        return normalized
    # =====================================================
    # Current DateTime Text
    # =====================================================
    def _now_text(
        self,
    ) -> str:
        """
        คืนวันที่และเวลาปัจจุบันสำหรับบันทึกลง SQLite
        """
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    # =====================================================
    # Table Exists
    # =====================================================
    def _table_exists(
        self,
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        """
        ตรวจสอบว่ามี Table อยู่ใน SQLite หรือไม่
        """

        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
            AND name = ?
            LIMIT 1
            """,
            (
                table_name,
            ),
        ).fetchone()

        return row is not None