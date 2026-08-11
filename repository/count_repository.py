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
              AND TRIM(pd.item_code) = TRIM((SELECT item_code FROM tb_item WHERE item_id = ? LIMIT 1))
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
              AND EXISTS (
                    SELECT 1
                    FROM tb_sync_queue AS q
                    WHERE q.source_table = 'tbt_count_history'
                      AND q.source_id = h.history_id
                      AND q.sync_type = 'COUNT'
                      AND COALESCE(q.sync_status, 'PENDING') <> 'SYNCED'
              )
            ORDER BY h.history_id DESC
            LIMIT ?
            """,
            (plan_id, limit),
        )

    def get_plan_detail_any_location(self, plan_id, item_id):
        """หารายการสินค้าใน Plan โดยไม่บังคับ Location เพื่อแยกกรณีผิด Location."""
        return self.find_one(
            """
            SELECT pd.*, i.item_code, i.item_name, i.uom
            FROM tb_plan_detail AS pd
            INNER JOIN tb_item AS i ON i.item_id=pd.item_id
            WHERE pd.plan_id=?
              AND TRIM(pd.item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
            ORDER BY pd.plan_detail_id
            LIMIT 1
            """, (int(plan_id), int(item_id))
        )

    def create_local_plan_detail(self, plan_id, item_id, location_id):
        """สร้าง Plan Detail ชั่วคราวด้วย ID ติดลบ; Server จะสร้าง ID จริงตอน Process."""
        connection=self.db.get_connection(); cur=connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            item=cur.execute("SELECT item_id,item_code FROM tb_item WHERE item_id=? LIMIT 1",(int(item_id),)).fetchone()
            loc=cur.execute("SELECT location_id,location_code,location_name FROM tb_location WHERE plan_id=? AND location_id=? LIMIT 1",(int(plan_id),int(location_id))).fetchone()
            if not item or not loc: raise ValueError("ข้อมูลสินค้า/Location สำหรับสร้างรายการใหม่ไม่ครบ")
            old=cur.execute("SELECT plan_detail_id FROM tb_plan_detail WHERE plan_id=? AND TRIM(item_code)=TRIM(?) AND location_id=? LIMIT 1",(int(plan_id),item['item_code'],int(location_id))).fetchone()
            if old:
                connection.commit(); return int(old['plan_detail_id'])
            row=cur.execute("SELECT MIN(plan_detail_id) AS min_id FROM tb_plan_detail WHERE plan_detail_id < 0").fetchone()
            local_id=(int(row['min_id'])-1) if row and row['min_id'] is not None else -1
            cur.execute("""
                INSERT INTO tb_plan_detail
                (plan_detail_id,plan_id,item_code,item_id,source_item_id,location_id,
                 new_location,before_location,qty,qty_on_hand,qty_audit,is_change_location,
                 local_is_changed,local_sync_status,count_sync_status,audit_sync_status)
                VALUES (?,?,?,?,?,?,?,NULL,0,0,0,1,1,'PENDING','NONE','NONE')
            """,(local_id,int(plan_id),item['item_code'],int(item_id),int(item_id),int(location_id),loc['location_code']))
            connection.commit(); return local_id
        except Exception:
            connection.rollback(); raise
        finally:
            cur.close(); connection.close()

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

    def _get_editable_queue(self, cursor, history_id):
        row = cursor.execute(
            """
            SELECT q.*
            FROM tb_sync_queue AS q
            WHERE q.source_table = 'tbt_count_history'
              AND q.source_id = ?
              AND q.sync_type = 'COUNT'
            ORDER BY q.queue_id DESC
            LIMIT 1
            """,
            (int(history_id),),
        ).fetchone()

        if row is None:
            raise ValueError("ไม่พบ Queue ของรายการที่ต้องการแก้")

        status = str(row["sync_status"] or "PENDING").upper()
        if status in ("SYNCING", "SYNCED"):
            raise ValueError("รายการนี้กำลัง Sync หรือ Sync แล้ว ไม่สามารถแก้ไขได้")
        if status not in ("PENDING", "ERROR"):
            raise ValueError(f"สถานะรายการ {status} ไม่อนุญาตให้แก้ไข")

        return row

    @staticmethod
    def _queue_payload(queue_row):
        try:
            payload = json.loads(queue_row["payload_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Payload ของรายการไม่ถูกต้อง") from exc
        if not isinstance(payload, dict):
            raise ValueError("Payload ของรายการไม่ถูกต้อง")
        return payload

    def update_pending_qty(self, history_id, new_qty, checker):
        """แก้ Qty ของ COUNT ที่ยังไม่ Sync และปรับ Queue เดิมเท่านั้น."""
        connection = self.db.get_connection()
        cursor = connection.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            connection.execute("BEGIN IMMEDIATE")

            source = cursor.execute(
                """
                SELECT *
                FROM tbt_count_history
                WHERE history_id = ?
                  AND COALESCE(is_audit, 0) = 0
                LIMIT 1
                """,
                (int(history_id),),
            ).fetchone()
            if source is None:
                raise ValueError("ไม่พบ Transaction ของรายการที่ต้องการแก้")

            queue = self._get_editable_queue(cursor, history_id)
            payload = self._queue_payload(queue)
            payload.update({
                "history_id": int(history_id),
                "transaction_guid": str(source["transaction_guid"]),
                "reference_transaction_guid": None,
                "transaction_type": "COUNT",
                "operation_type": "INSERT",
                "qty": float(new_qty),
                "qty_on_hand": float(new_qty),
                "checker": str(checker or ""),
                "is_audit": 0,
                "audit_round": 0,
                "check_date": now,
                "transaction_date": now,
                "modified_at": now,
            })
            payload.pop("correction_type", None)

            cursor.execute(
                """
                UPDATE tbt_count_history
                SET reference_transaction_guid=NULL,
                    operation_type='INSERT',
                    qty = ?, checker = ?
                WHERE history_id = ?
                """,
                (float(new_qty), checker, int(history_id)),
            )

            aggregate_row = cursor.execute(
                """
                SELECT COALESCE(SUM(qty), 0) AS total_qty
                FROM tbt_count_history
                WHERE plan_id = ?
                  AND plan_detail_id = ?
                  AND COALESCE(is_audit, 0) = 0
                """,
                (source["plan_id"], source["plan_detail_id"]),
            ).fetchone()
            total_qty = float(aggregate_row["total_qty"] or 0)

            cursor.execute(
                """
                UPDATE tb_plan_detail
                SET qty_on_hand = ?, checker = ?, check_date = ?,
                    count_sync_status = 'PENDING',
                    count_modified_at = ?, local_is_changed = 1,
                    local_sync_status = 'PENDING', local_updated_at = ?
                WHERE plan_detail_id = ? AND plan_id = ?
                """,
                (
                    total_qty, checker, now, now, now,
                    source["plan_detail_id"], source["plan_id"],
                ),
            )

            cursor.execute(
                """
                UPDATE tb_sync_queue
                SET payload_json = ?, sync_status = 'PENDING',
                    retry_count = 0, error_message = NULL,
                    last_attempt_at = NULL, synced_at = NULL
                WHERE queue_id = ?
                """,
                (json.dumps(payload, ensure_ascii=False), queue["queue_id"]),
            )

            connection.commit()
            return {
                "success": True,
                "history_id": int(history_id),
                "transaction_guid": source["transaction_guid"],
                "plan_id": source["plan_id"],
                "plan_detail_id": source["plan_detail_id"],
                "item_id": source["item_id"],
                "location_id": source["location_id"],
                "barcode": source["barcode"],
                "qty": float(new_qty),
                "checker": checker,
            }
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
        """แก้ Location ของ COUNT ที่ยังไม่ Sync และปรับ Queue เดิมเท่านั้น."""
        ids = [int(value) for value in history_ids]
        if not ids:
            return {"updated": 0}

        placeholders = ",".join("?" for _ in ids)
        connection = self.db.get_connection()
        cursor = connection.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = cursor.execute(
                f"""
                SELECT *
                FROM tbt_count_history
                WHERE plan_id = ?
                  AND history_id IN ({placeholders})
                  AND COALESCE(is_audit, 0) = 0
                """,
                [int(plan_id), *ids],
            ).fetchall()

            if len(rows) != len(ids):
                raise ValueError("พบบางรายการไม่ครบหรือไม่อยู่ใน Plan นี้")

            updated_details = set()
            for row in rows:
                history_id = int(row["history_id"])
                queue = self._get_editable_queue(cursor, history_id)
                payload = self._queue_payload(queue)
                payload.update({
                    "history_id": history_id,
                    "transaction_guid": str(row["transaction_guid"]),
                    "reference_transaction_guid": None,
                    "transaction_type": "COUNT",
                    "operation_type": "INSERT",
                    "location_id": int(new_location_id),
                    "location_code": str(new_location_code or "").strip(),
                    "checker": str(checker or ""),
                    "is_audit": 0,
                    "audit_round": 0,
                    "modified_at": now,
                })
                payload.pop("correction_type", None)

                cursor.execute(
                    """
                    UPDATE tbt_count_history
                    SET reference_transaction_guid=NULL,
                        operation_type='INSERT',
                        location_id = ?, checker = ?
                    WHERE history_id = ?
                    """,
                    (int(new_location_id), checker, history_id),
                )

                plan_detail_id = int(row["plan_detail_id"])
                if plan_detail_id not in updated_details:
                    cursor.execute(
                        """
                        UPDATE tb_plan_detail
                        SET location_id = ?, new_location = ?,
                            is_change_location = 1, checker = ?,
                            count_sync_status = 'PENDING',
                            count_modified_at = ?, local_is_changed = 1,
                            local_sync_status = 'PENDING', local_updated_at = ?
                        WHERE plan_detail_id = ? AND plan_id = ?
                        """,
                        (
                            int(new_location_id), str(new_location_code or "").strip(),
                            checker, now, now, plan_detail_id, int(plan_id),
                        ),
                    )
                    updated_details.add(plan_detail_id)

                cursor.execute(
                    """
                    UPDATE tb_sync_queue
                    SET payload_json = ?, sync_status = 'PENDING',
                        retry_count = 0, error_message = NULL,
                        last_attempt_at = NULL, synced_at = NULL
                    WHERE queue_id = ?
                    """,
                    (json.dumps(payload, ensure_ascii=False), queue["queue_id"]),
                )

            connection.commit()
            return {
                "success": True,
                "updated": len(rows),
                "location_id": int(new_location_id),
                "location_code": str(new_location_code or "").strip(),
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
