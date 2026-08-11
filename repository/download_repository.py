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

                self._resolve_detail_locations(connection, plan_id)

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

        ใช้ Clean Schema ซึ่งมี tb_sync_queue.plan_id เสมอ
        """

        plan_id = self._to_int(
            plan_id
        )

        if plan_id <= 0:
            raise DownloadRepositoryError(
                "Plan ID สำหรับตรวจสอบข้อมูลรอ Sync ไม่ถูกต้อง"
            )

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
    
    # =====================================================
    # create_tb_audit_history
    # =====================================================
        
    
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
    # =====================================================
    # Table: tb_plan
    # =====================================================
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
    # Upgrade Existing Schema
    # =====================================================
    # =====================================================
    # Create Indexes
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
    # Delete Existing Plan Data
    # =====================================================
    def _delete_existing_plan(
        self,
        connection: sqlite3.Connection,
        plan_id: int,
    ) -> None:
        """Delete one downloaded plan after pending-sync validation."""
        plan_id = self._to_int(plan_id)
        if plan_id <= 0:
            raise DownloadRepositoryError("Plan ID สำหรับลบข้อมูลเดิมไม่ถูกต้อง")

        for table_name in (
            "tb_sync_queue",
            "tb_audit_history",
            "tbt_count_history",
            "tb_download_log",
            "tb_plan_detail",
            "tb_location",
            "tb_plan",
        ):
            connection.execute(
                f"DELETE FROM {table_name} WHERE plan_id = ?",
                (plan_id,),
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
        - qty, qty_on_hand, qty_audit และ server_qty_audit รับค่าจาก Server
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
            item_code = self._to_text(detail.get("item_code"))
            location_id = self._to_int(detail.get("location_id"))

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
            if not item_code:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} ไม่มี item_code"
                )
            if location_id <= 0:
                raise DownloadRepositoryError(
                    f"Plan Detail แถวที่ {index:,} ไม่มี location_id ที่ถูกต้อง"
                )

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
                    "item_code": item_code,
                    "item_id": item_id,
                    "location_id": location_id,
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
                    "server_qty_audit": self._to_float(
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
                item_code,
                item_id,
                source_item_id,
                location_id,

                new_zone,
                before_zone,
                new_location,
                before_location,

                qty,
                qty_on_hand,
                qty_audit,
                server_qty_audit,

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
                :item_code,
                :item_id,
                :source_item_id,
                :location_id,

                :new_zone,
                :before_zone,
                :new_location,
                :before_location,

                :qty,
                :qty_on_hand,
                :qty_audit,
                :server_qty_audit,

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
        - server_qty_audit รับค่าจาก Server เสมอ
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
            if not item_code:
                raise DownloadRepositoryError(
                    f"Refresh Detail แถวที่ {index:,} ไม่มี item_code"
                )
            if location_id <= 0:
                raise DownloadRepositoryError(
                    f"Refresh Detail แถวที่ {index:,} ไม่มี location_id ที่ถูกต้อง"
                )

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
                    "item_code": item_code,
                    "item_id": item_id,
                    "location_id": location_id,
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
                    "server_qty_audit": self._to_float(
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
                item_code,
                item_id,
                source_item_id,
                location_id,

                new_zone,
                before_zone,
                new_location,
                before_location,

                qty,
                qty_on_hand,
                qty_audit,
                server_qty_audit,

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
                :item_code,
                :item_id,
                :source_item_id,
                :location_id,

                :new_zone,
                :before_zone,
                :new_location,
                :before_location,

                :qty,
                :qty_on_hand,
                :qty_audit,
                :server_qty_audit,

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
                item_code = excluded.item_code,
                item_id = excluded.item_id,
                location_id = excluded.location_id,
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
                Snapshot Audit จาก Server ต้องอัปเดตทุกครั้งที่ Refresh
                และไม่ถูก Local Audit แก้ไข
                */
                server_qty_audit = excluded.server_qty_audit,

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
    def _resolve_detail_locations(
        self,
        connection: sqlite3.Connection,
        plan_id: int,
    ) -> None:
        """Validate location_id supplied by DownloadPlan.ashx.

        The server is the authority for location_id. This method never remaps or
        overwrites it from before_location/new_location.
        """
        missing_rows = connection.execute(
            """
            SELECT pd.plan_detail_id, pd.location_id
            FROM tb_plan_detail AS pd
            LEFT JOIN tb_location AS l
              ON l.plan_id = pd.plan_id
             AND l.location_id = pd.location_id
            WHERE pd.plan_id = ?
              AND (pd.location_id IS NULL OR pd.location_id <= 0 OR l.location_id IS NULL)
            ORDER BY pd.plan_detail_id
            LIMIT 20
            """,
            (int(plan_id),),
        ).fetchall()
        if missing_rows:
            sample = ", ".join(
                f"{row['plan_detail_id']}:{row['location_id']}" for row in missing_rows
            )
            raise DownloadRepositoryError(
                "Location ID ใน Plan Detail ไม่ตรงกับรายการ Location ที่ Server ส่งมา: " + sample
            )

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
            - item_code ซ้ำได้เมื่อเป็นคนละ item_id
        """
        if not items:
            raise DownloadRepositoryError(
                "ไม่พบข้อมูลสินค้าใน Download Package"
            )
        item_ids = set()
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
            if item_id in item_ids:
                raise DownloadRepositoryError(
                    f"พบ item_id ซ้ำ: {item_id}"
                )
            item_ids.add(
                item_id
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