"""
=========================================================
Project : HWK_StockV1
File    : repository/count_repository.py
Count Repository
=========================================================
"""

import json
import uuid
from datetime import datetime

from repository.base_repository import BaseRepository
from models.count_transaction import CountTransaction


class CountRepository(BaseRepository):
    def find_location(self, plan_id, scan_value):
        scan_value = str(scan_value or "").strip()
        if not scan_value:
            return None

        return self.find_one(
            """
            SELECT location_id, location_name, plan_id, location_code, downloaded_at
            FROM tb_location
            WHERE plan_id = ?
              AND (
                    TRIM(COALESCE(CAST(location_id AS TEXT), '')) = TRIM(?)
                 OR TRIM(COALESCE(location_code, '')) = TRIM(?)
                 OR TRIM(COALESCE(location_name, '')) = TRIM(?)
              )
            LIMIT 1
            """,
            (plan_id, scan_value, scan_value, scan_value),
        )


    def get_location_by_id(self, plan_id, location_id):
        """คืน Location ของ Plan จาก Server location_id ที่เก็บใน SQLite"""
        return self.find_one(
            """
            SELECT location_id, location_code, location_name, plan_id, downloaded_at
            FROM tb_location
            WHERE plan_id = ?
              AND CAST(location_id AS TEXT) = CAST(? AS TEXT)
            LIMIT 1
            """,
            (plan_id, location_id),
        )

    def _attach_server_location(self, payload, plan_id, location_id):
        """เติม location_code และบังคับ location_id ให้เป็นค่าจาก Download/SQL Server"""
        location = self.get_location_by_id(plan_id, location_id)
        if not location:
            raise ValueError(
                f"ไม่พบ Server Location ID {location_id} ใน Plan {plan_id}; กรุณา Download Plan ใหม่"
            )
        payload["location_id"] = int(location["location_id"])
        payload["location_code"] = str(location["location_code"] or "").strip()
        return payload

    def find_item_by_barcode(self, barcode):
        return self.find_one(
            """
            SELECT i.*, b.barcode
            FROM tb_barcode AS b
            INNER JOIN tb_item AS i ON i.item_id = b.item_id
            WHERE TRIM(b.barcode) = TRIM(?)
            LIMIT 1
            """,
            (barcode,),
        )

    def find_item_by_code(self, item_code):
        return self.find_one(
            """
            SELECT i.*, i.item_code AS barcode
            FROM tb_item AS i
            WHERE TRIM(i.item_code) = TRIM(?)
            LIMIT 1
            """,
            (item_code,),
        )

    def find_item(self, scan_value):
        scan_value = str(scan_value or "").strip()
        if not scan_value:
            return None

        return self.find_one(
            """
            SELECT DISTINCT
                i.item_id, i.item_code, i.item_name, i.uom,
                i.category, i.unit_rate, i.qty, i.unit_cost,
                i.batching_unit, i.batching_factor, i.is_active,
                i.downloaded_at, i.updated_at
            FROM tb_item AS i
            LEFT JOIN tb_barcode AS b ON b.item_id = i.item_id
            WHERE COALESCE(i.is_active, 1) = 1
              AND (
                    TRIM(COALESCE(i.item_code, '')) = TRIM(?)
                 OR TRIM(COALESCE(b.barcode, '')) = TRIM(?)
              )
            LIMIT 1
            """,
            (scan_value, scan_value),
        )

    def get_plan_detail(self, plan_id, item_id, location_id):
        return self.find_one(
            """
            SELECT
                pd.*,
                COALESCE(pd.source_item_id, pd.item_id) AS effective_source_item_id,
                i.item_code,
                i.item_name,
                i.uom,
                l.location_code,
                l.location_name
            FROM tb_plan_detail AS pd
            INNER JOIN tb_item AS i ON i.item_id = pd.item_id
            LEFT JOIN tb_location AS l
                   ON l.plan_id = pd.plan_id
                  AND (
                        CAST(l.location_id AS TEXT) = CAST(pd.location_id AS TEXT)
                     OR TRIM(l.location_code) = TRIM(COALESCE(NULLIF(pd.new_location, ''), pd.before_location))
                  )
            WHERE pd.plan_id = ?
              AND pd.item_id = ?
              AND (
                    CAST(pd.location_id AS TEXT) = CAST(? AS TEXT)
                 OR TRIM(COALESCE(NULLIF(pd.new_location, ''), pd.before_location)) = (
                        SELECT TRIM(location_code)
                        FROM tb_location
                        WHERE plan_id = ?
                          AND CAST(location_id AS TEXT) = CAST(? AS TEXT)
                        LIMIT 1
                    )
              )
            LIMIT 1
            """,
            (plan_id, item_id, location_id, plan_id, location_id),
        )

    def get_plan_detail_by_id(self, plan_detail_id):
        return self.find_one(
            """
            SELECT
                pd.*,
                COALESCE(pd.source_item_id, pd.item_id) AS effective_source_item_id,
                i.item_code,
                i.item_name,
                i.uom,
                l.location_code,
                l.location_name
            FROM tb_plan_detail AS pd
            INNER JOIN tb_item AS i ON i.item_id = pd.item_id
            LEFT JOIN tb_location AS l
                   ON l.plan_id = pd.plan_id
                  AND (
                        CAST(l.location_id AS TEXT) = CAST(pd.location_id AS TEXT)
                     OR TRIM(l.location_code) = TRIM(COALESCE(NULLIF(pd.new_location, ''), pd.before_location))
                  )
            WHERE pd.plan_detail_id = ?
            LIMIT 1
            """,
            (plan_detail_id,),
        )

    def get_current_qty(self, plan_detail_id):
        return self.find_one(
            """
            SELECT qty_on_hand, checker, check_date, count_sync_status,
                   count_transaction_guid, count_modified_at
            FROM tb_plan_detail
            WHERE plan_detail_id = ?
            LIMIT 1
            """,
            (plan_detail_id,),
        )

    def get_recent_counts(self, plan_id, limit=5):
        return self.find_all(
            """
            SELECT
                h.history_id,
                h.transaction_guid,
                h.plan_id,
                h.plan_detail_id,
                h.item_id,
                h.location_id,
                h.barcode,
                h.qty,
                h.checker,
                h.create_date,
                i.item_code,
                i.item_name,
                i.uom,
                COALESCE(
                    NULLIF(TRIM(l.location_code), ''),
                    NULLIF(TRIM(pd.new_location), ''),
                    NULLIF(TRIM(pd.before_location), ''),
                    CAST(h.location_id AS TEXT)
                ) AS location_code,
                COALESCE(NULLIF(TRIM(l.location_name), ''), '') AS location_name
            FROM tbt_count_history AS h
            INNER JOIN tb_item AS i
                    ON i.item_id = h.item_id
            LEFT JOIN tb_plan_detail AS pd
                   ON pd.plan_detail_id = h.plan_detail_id
            LEFT JOIN tb_location AS l
                   ON l.plan_id = h.plan_id
                  AND (
                        CAST(l.location_id AS TEXT) = CAST(h.location_id AS TEXT)
                     OR TRIM(l.location_code) = TRIM(COALESCE(NULLIF(pd.new_location, ''), pd.before_location))
                  )
            WHERE h.plan_id = ?
              AND COALESCE(h.is_audit, 0) = 0
            ORDER BY h.history_id DESC
            LIMIT ?
            """,
            (plan_id, limit),
        )

    def save_count(self, transaction: CountTransaction):
        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")

            cursor.execute(
                """
                SELECT plan_detail_id, plan_id, item_id, location_id
                FROM tb_plan_detail
                WHERE plan_detail_id = ?
                LIMIT 1
                """,
                (transaction.plan_detail_id,),
            )
            detail = cursor.fetchone()
            if detail is None:
                raise ValueError("ไม่พบรายการสินค้าในแผนตรวจนับ")
            if int(detail["plan_id"]) != int(transaction.plan_id):
                raise ValueError("Plan ID ของรายการไม่ถูกต้อง")
            if int(detail["item_id"]) != int(transaction.item_id):
                raise ValueError("Item ID ของรายการไม่ถูกต้อง")
            # Older downloaded plans can have NULL location_id and keep the
            # actual rack in before_location/new_location. Selection is already
            # validated by get_plan_detail(), so do not reject those records here.

            cursor.execute(
                """
                UPDATE tb_plan_detail
                SET qty_on_hand = ?, checker = ?, check_date = ?, is_check = 1,
                    count_sync_status = 'PENDING', count_transaction_guid = ?,
                    count_modified_at = ?, local_is_changed = 1,
                    local_sync_status = 'PENDING', local_updated_at = ?
                WHERE plan_detail_id = ?
                """,
                (
                    transaction.qty, transaction.checker, transaction.create_date,
                    transaction.transaction_guid, transaction.create_date,
                    transaction.create_date, transaction.plan_detail_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("ไม่สามารถปรับปรุงจำนวนตรวจนับได้")

            cursor.execute(
                """
                INSERT INTO tbt_count_history
                    (transaction_guid, plan_id, plan_detail_id, item_id,
                     location_id, barcode, qty, checker, is_audit, create_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    transaction.transaction_guid, transaction.plan_id,
                    transaction.plan_detail_id, transaction.item_id,
                    transaction.location_id, transaction.barcode,
                    transaction.qty, transaction.checker, transaction.create_date,
                ),
            )
            history_id = cursor.lastrowid

            payload = self._attach_server_location(
                transaction.to_dict(),
                transaction.plan_id,
                transaction.location_id,
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO tb_sync_queue
                    (plan_id, plan_detail_id, transaction_guid, sync_type,
                     transaction_type, source_table, source_id, payload_json,
                     sync_status, retry_count, create_date, created_at)
                VALUES (?, ?, ?, 'COUNT', 'COUNT', 'tbt_count_history', ?, ?,
                        'PENDING', 0, ?, ?)
                """,
                (
                    transaction.plan_id, transaction.plan_detail_id,
                    transaction.transaction_guid, history_id,
                    json.dumps(payload, ensure_ascii=False),
                    transaction.create_date, transaction.create_date,
                ),
            )

            connection.commit()
            return {
                "success": True,
                "plan_detail_id": transaction.plan_detail_id,
                "transaction_guid": transaction.transaction_guid,
                "qty_on_hand": transaction.qty,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def correction_qty(self, transaction: CountTransaction, reference_transaction_guid=None):
        """แก้จำนวนในเครื่องและสร้าง Queue ที่อ้างถึง COUNT เดิม"""
        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                UPDATE tb_plan_detail
                SET qty_on_hand=?, checker=?, check_date=?,
                    count_sync_status='PENDING', count_transaction_guid=?,
                    count_modified_at=?, local_is_changed=1,
                    local_sync_status='PENDING', local_updated_at=?
                WHERE plan_detail_id=? AND plan_id=?
                """,
                (
                    transaction.qty, transaction.checker, transaction.create_date,
                    transaction.transaction_guid, transaction.create_date,
                    transaction.create_date, transaction.plan_detail_id,
                    transaction.plan_id,
                ),
            )
            cursor.execute(
                """
                INSERT INTO tbt_count_history
                    (transaction_guid, plan_id, plan_detail_id, item_id,
                     location_id, barcode, qty, checker, is_audit, create_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    transaction.transaction_guid, transaction.plan_id,
                    transaction.plan_detail_id, transaction.item_id,
                    transaction.location_id, transaction.barcode,
                    transaction.qty, transaction.checker, transaction.create_date,
                ),
            )
            history_id = cursor.lastrowid
            payload = self._attach_server_location(
                transaction.to_dict(),
                transaction.plan_id,
                transaction.location_id,
            )
            payload["operation_type"] = "UPDATE_QTY"
            payload["reference_transaction_guid"] = reference_transaction_guid
            payload["history_id"] = history_id
            cursor.execute(
                """
                INSERT OR IGNORE INTO tb_sync_queue
                    (plan_id, plan_detail_id, transaction_guid, sync_type,
                     transaction_type, source_table, source_id, payload_json,
                     sync_status, retry_count, create_date, created_at)
                VALUES (?, ?, ?, 'CORRECTION_QTY', 'CORRECTION_QTY',
                        'tbt_count_history', ?, ?, 'PENDING', 0, ?, ?)
                """,
                (
                    transaction.plan_id, transaction.plan_detail_id,
                    transaction.transaction_guid, history_id,
                    json.dumps(payload, ensure_ascii=False),
                    transaction.create_date, transaction.create_date,
                ),
            )
            connection.commit()
            return {"success": True, "transaction_guid": transaction.transaction_guid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()


    def correct_locations(
        self,
        plan_id,
        history_ids,
        new_location_id,
        new_location_code,
        checker,
    ):
        """เปลี่ยน Location หลายรายการใน SQLite และสร้าง Queue รอ Sync"""
        ids = [int(value) for value in history_ids]
        if not ids:
            return {"updated": 0}

        placeholders = ",".join("?" for _ in ids)
        connection = self.db.get_connection()
        cursor = connection.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            connection.execute("BEGIN IMMEDIATE")

            cursor.execute(
                f"""
                SELECT
                    h.history_id, h.plan_id, h.plan_detail_id, h.item_id,
                    h.barcode, h.qty, h.transaction_guid
                FROM tbt_count_history AS h
                WHERE h.plan_id = ?
                  AND h.history_id IN ({placeholders})
                  AND COALESCE(h.is_audit, 0) = 0
                """,
                [plan_id, *ids],
            )
            rows = cursor.fetchall()

            if len(rows) != len(ids):
                raise ValueError("พบบางรายการไม่ครบหรือไม่อยู่ใน Plan นี้")

            updated_details = set()

            for row in rows:
                history_id = row["history_id"]
                plan_detail_id = row["plan_detail_id"]

                cursor.execute(
                    """
                    UPDATE tbt_count_history
                    SET location_id = ?, checker = ?
                    WHERE history_id = ?
                    """,
                    (new_location_id, checker, history_id),
                )

                if plan_detail_id not in updated_details:
                    cursor.execute(
                        """
                        UPDATE tb_plan_detail
                        SET location_id = ?,
                            new_location = ?,
                            is_change_location = 1,
                            checker = ?,
                            count_sync_status = 'PENDING',
                            count_modified_at = ?,
                            local_is_changed = 1,
                            local_sync_status = 'PENDING',
                            local_updated_at = ?
                        WHERE plan_detail_id = ?
                          AND plan_id = ?
                        """,
                        (
                            new_location_id, new_location_code, checker, now,
                            now, plan_detail_id, plan_id,
                        ),
                    )
                    updated_details.add(plan_detail_id)

                queue_guid = str(uuid.uuid4())
                payload = {
                    "history_id": history_id,
                    "plan_id": plan_id,
                    "plan_detail_id": plan_detail_id,
                    "item_id": row["item_id"],
                    "barcode": row["barcode"],
                    "qty": row["qty"],
                    "location_id": new_location_id,
                    "location_code": new_location_code,
                    "checker": checker,
                    "correction_type": "LOCATION",
                    "operation_type": "UPDATE_LOCATION",
                    "reference_transaction_guid": row["transaction_guid"],
                    "modified_at": now,
                }

                cursor.execute(
                    """
                    INSERT INTO tb_sync_queue
                        (plan_id, plan_detail_id, transaction_guid, sync_type,
                         transaction_type, source_table, source_id, payload_json,
                         sync_status, retry_count, create_date, created_at)
                    VALUES (?, ?, ?, 'CORRECTION_LOCATION',
                            'CORRECTION_LOCATION', 'tbt_count_history', ?, ?,
                            'PENDING', 0, ?, ?)
                    """,
                    (
                        plan_id, plan_detail_id, queue_guid, history_id,
                        json.dumps(payload, ensure_ascii=False), now, now,
                    ),
                )

            connection.commit()
            return {
                "updated": len(rows),
                "location_id": new_location_id,
                "location_code": new_location_code,
            }

        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def has_local_pending_count(self, plan_detail_id):
        row = self.find_one(
            """
            SELECT 1 AS found
            FROM tb_plan_detail
            WHERE plan_detail_id = ?
              AND count_sync_status IN ('PENDING', 'SYNCING', 'ERROR')
            LIMIT 1
            """,
            (plan_detail_id,),
        )
        return row is not None
