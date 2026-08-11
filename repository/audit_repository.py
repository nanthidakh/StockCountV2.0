"""Audit repository. All Audit writes are atomic."""
import json
from datetime import datetime

from models.count_transaction import CountTransaction, OperationType, TransactionType


class AuditRepository:
    def __init__(self, db):
        self.db = db

    def get_current_plan(self):
        return self.db.query_one("""
            SELECT p.*, COUNT(pd.plan_detail_id) AS total_items
            FROM tb_plan p
            LEFT JOIN tb_plan_detail pd ON pd.plan_id=p.plan_id
            GROUP BY p.plan_id
            ORDER BY COALESCE(p.download_date,p.update_date,p.create_date) DESC, p.plan_id DESC
            LIMIT 1
        """)

    def find_location(self, plan_id, scan_value):
        scan_value = str(scan_value or "").strip()
        return self.db.query_one("""
            SELECT location_id, location_code, location_name, plan_id
            FROM tb_location
            WHERE plan_id=? AND (
                TRIM(CAST(location_id AS TEXT))=TRIM(?) OR
                TRIM(COALESCE(location_code,''))=TRIM(?) OR
                TRIM(COALESCE(location_name,''))=TRIM(?)
            ) LIMIT 1
        """, (int(plan_id), scan_value, scan_value, scan_value))

    def find_item(self, scan_value):
        scan_value = str(scan_value or "").strip()
        return self.db.query_one("""
            SELECT DISTINCT i.*
            FROM tb_item i
            LEFT JOIN tb_barcode b ON b.item_id=i.item_id
            WHERE COALESCE(i.is_active,1)=1
              AND (TRIM(COALESCE(i.item_code,''))=TRIM(?) OR TRIM(COALESCE(b.barcode,''))=TRIM(?))
            LIMIT 1
        """, (scan_value, scan_value))

    def get_audit_detail(self, plan_id, item_id, location_id):
        return self.db.query_one("""
            SELECT pd.*, i.item_code, i.item_name, i.uom,
                   l.location_code, l.location_name
            FROM tb_plan_detail pd
            JOIN tb_item i ON i.item_id=pd.item_id
            LEFT JOIN tb_location l ON l.plan_id=pd.plan_id AND CAST(l.location_id AS TEXT)=CAST(? AS TEXT)
            WHERE pd.plan_id=?
              AND TRIM(pd.item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
              AND (
                    CAST(pd.location_id AS TEXT)=CAST(? AS TEXT)
                 OR TRIM(COALESCE(NULLIF(pd.new_location,''),pd.before_location))=TRIM(COALESCE(l.location_code,''))
              )
            LIMIT 1
        """, (location_id, int(plan_id), int(item_id), location_id))

    def get_audit_detail_any_location(self, plan_id, item_id):
        return self.db.query_one("""
            SELECT pd.*, i.item_code, i.item_name, i.uom
            FROM tb_plan_detail pd JOIN tb_item i ON i.item_id=pd.item_id
            WHERE pd.plan_id=? AND TRIM(pd.item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
            ORDER BY pd.plan_detail_id LIMIT 1
        """, (int(plan_id), int(item_id)))

    def create_local_plan_detail(self, plan_id, item_id, location_id):
        connection=self.db.get_connection(); cur=connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            item=cur.execute("SELECT item_id,item_code FROM tb_item WHERE item_id=? LIMIT 1",(int(item_id),)).fetchone()
            loc=cur.execute("SELECT location_id,location_code FROM tb_location WHERE plan_id=? AND location_id=? LIMIT 1",(int(plan_id),int(location_id))).fetchone()
            if not item or not loc: raise ValueError("ข้อมูลสินค้า/Location สำหรับสร้างรายการใหม่ไม่ครบ")
            old=cur.execute("SELECT plan_detail_id FROM tb_plan_detail WHERE plan_id=? AND TRIM(item_code)=TRIM(?) AND location_id=? LIMIT 1",(int(plan_id),item['item_code'],int(location_id))).fetchone()
            if old: connection.commit(); return int(old['plan_detail_id'])
            row=cur.execute("SELECT MIN(plan_detail_id) AS min_id FROM tb_plan_detail WHERE plan_detail_id < 0").fetchone()
            local_id=(int(row['min_id'])-1) if row and row['min_id'] is not None else -1
            cur.execute("""INSERT INTO tb_plan_detail
                (plan_detail_id,plan_id,item_code,item_id,source_item_id,location_id,new_location,
                 qty,qty_on_hand,qty_audit,is_change_location,local_is_changed,local_sync_status,count_sync_status,audit_sync_status)
                VALUES (?,?,?,?,?,?,?,0,0,0,1,1,'PENDING','NONE','NONE')""",
                (local_id,int(plan_id),item['item_code'],int(item_id),int(item_id),int(location_id),loc['location_code']))
            connection.commit(); return local_id
        except Exception:
            connection.rollback(); raise
        finally:
            cur.close(); connection.close()

    def find_duplicate(self, plan_id, item_id, location_id, audit_round):
        return self.db.query_one("""
            SELECT h.*, i.item_code, i.item_name, i.uom,
                   COALESCE(l.location_code,CAST(h.location_id AS TEXT)) AS location_code,
                   q.sync_status AS queue_status
            FROM tbt_count_history h
            INNER JOIN tb_sync_queue q
                    ON q.source_table='tbt_count_history'
                   AND q.source_id=h.history_id
                   AND q.sync_type='AUDIT'
            JOIN tb_item i ON i.item_id=h.item_id
            LEFT JOIN tb_location l ON l.plan_id=h.plan_id
                 AND CAST(l.location_id AS TEXT)=CAST(h.location_id AS TEXT)
            WHERE h.plan_id=?
              AND TRIM(i.item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
              AND CAST(h.location_id AS TEXT)=CAST(? AS TEXT)
              AND COALESCE(h.is_audit,0)=1
              AND COALESCE(h.audit_round,0)=?
            ORDER BY h.history_id DESC LIMIT 1
        """, (int(plan_id), int(item_id), str(location_id), int(audit_round)))

    def save_audit(self, transaction: CountTransaction, duplicate_mode="ADD"):
        """
        บันทึก Audit ใหม่ หรือปรับ Audit เดิมที่ยังไม่ Sync แบบ in-place.

        - รายการใหม่: INSERT History + Queue หนึ่งครั้ง
        - รายการซ้ำ PENDING/ERROR: UPDATE History + Queue เดิม
        - รายการ SYNCING/SYNCED: ห้ามแก้
        """
        if transaction.transaction_type != TransactionType.AUDIT:
            raise ValueError("Transaction ต้องเป็น AUDIT")
        if transaction.audit_round <= 0:
            raise ValueError("Audit Round ต้องมากกว่า 0")

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            detail = cursor.execute(
                """
                SELECT * FROM tb_plan_detail
                WHERE plan_detail_id=? AND plan_id=?
                  AND TRIM(item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
                LIMIT 1
                """,
                (transaction.plan_detail_id, transaction.plan_id, transaction.item_id),
            ).fetchone()
            if detail is None:
                raise ValueError("ไม่พบรายการ Audit ในใบงาน")

            old = cursor.execute(
                """
                SELECT h.*, q.queue_id, q.sync_status, q.payload_json
                FROM tbt_count_history h
                INNER JOIN tb_sync_queue q
                        ON q.source_table='tbt_count_history'
                       AND q.source_id=h.history_id
                       AND q.sync_type='AUDIT'
                INNER JOIN tb_item hi ON hi.item_id=h.item_id
                WHERE h.plan_id=?
                  AND TRIM(hi.item_code)=TRIM((SELECT item_code FROM tb_item WHERE item_id=? LIMIT 1))
                  AND CAST(h.location_id AS TEXT)=CAST(? AS TEXT)
                  AND COALESCE(h.is_audit,0)=1
                  AND COALESCE(h.audit_round,0)=?
                ORDER BY h.history_id DESC
                LIMIT 1
                """,
                (transaction.plan_id, transaction.item_id,
                 transaction.location_id, transaction.audit_round),
            ).fetchone()

            mode = str(duplicate_mode or "ADD").upper()
            if old and mode == "CANCEL":
                connection.rollback()
                return {"success": False, "cancelled": True}
            if mode not in ("ADD", "REPLACE"):
                raise ValueError("รูปแบบการบันทึก Audit ซ้ำไม่ถูกต้อง")

            location = cursor.execute(
                """
                SELECT location_code
                FROM tb_location
                WHERE plan_id=?
                  AND CAST(location_id AS TEXT)=CAST(? AS TEXT)
                LIMIT 1
                """,
                (transaction.plan_id, transaction.location_id),
            ).fetchone()
            location_code = location["location_code"] if location else None

            if old:
                status = str(old["sync_status"] or "PENDING").upper()
                if status not in ("PENDING", "ERROR"):
                    raise ValueError(
                        "รายการ Audit นี้กำลัง Sync หรือ Sync แล้ว ไม่สามารถแก้ไขได้"
                    )

                qty_to_save = float(transaction.qty)
                if mode == "ADD":
                    qty_to_save = float(old["qty"] or 0) + float(transaction.qty)

                payload = json.loads(old["payload_json"] or "{}")
                payload.update({
                    "history_id": int(old["history_id"]),
                    "transaction_guid": str(old["transaction_guid"]),
                    "reference_transaction_guid": None,
                    "transaction_type": "AUDIT",
                    "operation_type": "INSERT",
                    "plan_id": int(old["plan_id"]),
                    "plan_detail_id": int(old["plan_detail_id"]),
                    "item_id": int(old["item_id"]),
                    "location_id": old["location_id"],
                    "location_code": location_code,
                    "barcode": transaction.barcode,
                    "qty": qty_to_save,
                    "qty_audit": qty_to_save,
                    "checker": transaction.checker,
                    "auditor": transaction.checker,
                    "is_audit": 1,
                    "audit_round": int(old["audit_round"] or transaction.audit_round),
                    "create_date": transaction.create_date,
                    "audit_date": transaction.create_date,
                    "transaction_date": transaction.create_date,
                    "modified_at": transaction.create_date,
                })
                payload.pop("correction_type", None)

                cursor.execute(
                    """
                    UPDATE tbt_count_history
                    SET reference_transaction_guid=NULL,
                        operation_type='INSERT',
                        barcode=?, qty=?, checker=?, create_date=?
                    WHERE history_id=?
                    """,
                    (transaction.barcode, qty_to_save, transaction.checker,
                     transaction.create_date, old["history_id"]),
                )
                cursor.execute(
                    """
                    UPDATE tb_sync_queue
                    SET payload_json=?, sync_status='PENDING', retry_count=0,
                        error_message=NULL, create_date=?, created_at=?
                    WHERE queue_id=?
                    """,
                    (json.dumps(payload, ensure_ascii=False), transaction.create_date,
                     transaction.create_date, old["queue_id"]),
                )
                cursor.execute(
                    """
                    UPDATE tb_plan_detail
                    SET qty_audit=?, auditor=?, audit_date=?, audit_round=?,
                        audit_sync_status='PENDING', audit_transaction_guid=?,
                        audit_modified_at=?, local_is_changed=1,
                        local_sync_status='PENDING', local_updated_at=?
                    WHERE plan_detail_id=?
                    """,
                    (qty_to_save, transaction.checker, transaction.create_date,
                     int(old["audit_round"] or transaction.audit_round),
                     old["transaction_guid"], transaction.create_date,
                     transaction.create_date, transaction.plan_detail_id),
                )
                connection.commit()
                return {
                    "success": True,
                    "history_id": int(old["history_id"]),
                    "transaction_guid": str(old["transaction_guid"]),
                    "qty_audit": qty_to_save,
                    "operation_type": "INSERT",
                    "updated_existing": True,
                }

            transaction.operation_type = OperationType.INSERT
            transaction.reference_transaction_guid = None

            cursor.execute(
                """
                UPDATE tb_plan_detail
                SET qty_audit=?, auditor=?, audit_date=?, audit_round=?,
                    audit_sync_status='PENDING', audit_transaction_guid=?,
                    audit_modified_at=?, local_is_changed=1,
                    local_sync_status='PENDING', local_updated_at=?
                WHERE plan_detail_id=?
                """,
                (transaction.qty, transaction.checker, transaction.create_date,
                 transaction.audit_round, transaction.transaction_guid,
                 transaction.create_date, transaction.create_date,
                 transaction.plan_detail_id),
            )

            cursor.execute(
                """
                INSERT INTO tbt_count_history
                (transaction_guid,reference_transaction_guid,operation_type,
                 plan_id,plan_detail_id,item_id,location_id,barcode,qty,checker,
                 is_audit,audit_round,create_date)
                VALUES (?,NULL,'INSERT',?,?,?,?,?,?,?,1,?,?)
                """,
                (transaction.transaction_guid, transaction.plan_id,
                 transaction.plan_detail_id, transaction.item_id,
                 transaction.location_id, transaction.barcode, transaction.qty,
                 transaction.checker, transaction.audit_round,
                 transaction.create_date),
            )
            history_id = cursor.lastrowid

            payload = transaction.to_dict()
            payload.update({
                "history_id": history_id,
                "reference_transaction_guid": None,
                "operation_type": "INSERT",
                "location_code": location_code,
            })

            cursor.execute(
                """
                INSERT INTO tb_sync_queue
                (plan_id,plan_detail_id,transaction_guid,sync_type,transaction_type,
                 source_table,source_id,payload_json,sync_status,retry_count,create_date,created_at)
                VALUES (?,?,?,'AUDIT','AUDIT','tbt_count_history',?,?,'PENDING',0,?,?)
                """,
                (transaction.plan_id, transaction.plan_detail_id,
                 transaction.transaction_guid, history_id,
                 json.dumps(payload, ensure_ascii=False),
                 transaction.create_date, transaction.create_date),
            )
            connection.commit()
            return {
                "success": True,
                "history_id": history_id,
                "transaction_guid": transaction.transaction_guid,
                "qty_audit": transaction.qty,
                "operation_type": "INSERT",
                "updated_existing": False,
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def get_recent_audits(self, plan_id, limit=15):
        return self.db.query_all("""
            SELECT h.*, i.item_code, i.item_name, i.uom,
                   COALESCE(l.location_code,CAST(h.location_id AS TEXT)) AS location_code,
                   q.sync_status AS queue_status
            FROM tbt_count_history h
            INNER JOIN tb_sync_queue q
                    ON q.source_table='tbt_count_history'
                   AND q.source_id=h.history_id
                   AND q.sync_type='AUDIT'
            JOIN tb_item i ON i.item_id=h.item_id
            LEFT JOIN tb_location l ON l.plan_id=h.plan_id
              AND CAST(l.location_id AS TEXT)=CAST(h.location_id AS TEXT)
            WHERE h.plan_id=? AND COALESCE(h.is_audit,0)=1
              AND COALESCE(q.sync_status,'PENDING')<>'SYNCED'
            ORDER BY h.history_id DESC LIMIT ?
        """, (int(plan_id), int(limit)))

    def correct_qty(self, history_id, new_qty, auditor):
        """แก้ Record/Queue AUDIT เดิม เฉพาะรายการที่ยังไม่ Sync."""
        connection = self.db.get_connection()
        cursor = connection.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        try:
            connection.execute("BEGIN IMMEDIATE")
            source = cursor.execute(
                """
                SELECT h.*, q.queue_id, q.sync_status, q.payload_json
                FROM tbt_count_history h
                INNER JOIN tb_sync_queue q
                        ON q.source_table='tbt_count_history'
                       AND q.source_id=h.history_id
                       AND q.sync_type='AUDIT'
                WHERE h.history_id=? AND COALESCE(h.is_audit,0)=1
                LIMIT 1
                """,
                (int(history_id),),
            ).fetchone()
            if not source:
                raise ValueError("ไม่พบ Queue เดิมของรายการ Audit")
            status = str(source["sync_status"] or "PENDING").upper()
            if status in ("SYNCING", "SYNCED"):
                raise ValueError("รายการนี้กำลัง Sync หรือ Sync แล้ว ไม่สามารถแก้ไขได้")

            payload = json.loads(source["payload_json"] or "{}")
            payload.update({
                "history_id": int(source["history_id"]),
                "transaction_guid": str(source["transaction_guid"]),
                "reference_transaction_guid": None,
                "transaction_type": "AUDIT",
                "operation_type": "INSERT",
                "qty": float(new_qty),
                "qty_audit": float(new_qty),
                "checker": auditor,
                "auditor": auditor,
                "is_audit": 1,
                "audit_round": int(source["audit_round"] or 1),
                "create_date": now,
                "audit_date": now,
                "transaction_date": now,
                "modified_at": now,
            })
            payload.pop("correction_type", None)

            cursor.execute(
                """
                UPDATE tbt_count_history
                SET reference_transaction_guid=NULL,
                    operation_type='INSERT',
                    qty=?, checker=?, create_date=?
                WHERE history_id=?
                """,
                (float(new_qty), auditor, now, source["history_id"]),
            )
            cursor.execute(
                """
                UPDATE tb_plan_detail
                SET qty_audit=?, auditor=?, audit_date=?,
                    audit_sync_status='PENDING', audit_transaction_guid=?,
                    audit_modified_at=?, local_is_changed=1,
                    local_sync_status='PENDING', local_updated_at=?
                WHERE plan_detail_id=?
                """,
                (float(new_qty), auditor, now, source["transaction_guid"],
                 now, now, source["plan_detail_id"]),
            )
            cursor.execute(
                """
                UPDATE tb_sync_queue
                SET payload_json=?, sync_status='PENDING', retry_count=0,
                    error_message=NULL
                WHERE queue_id=?
                """,
                (json.dumps(payload, ensure_ascii=False), source["queue_id"]),
            )
            connection.commit()
            return {"success": True, "history_id": source["history_id"]}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

    def correct_locations(self, history_ids, new_location_id, auditor):
        """แก้ Location ใน Record/Queue AUDIT เดิม เฉพาะรายการที่ยังไม่ Sync."""
        ids = [int(value) for value in history_ids]
        if not ids:
            return {"success": True, "updated": 0}
        placeholders = ",".join("?" for _ in ids)
        connection = self.db.get_connection()
        cursor = connection.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = cursor.execute(
                f"""
                SELECT h.*, q.queue_id, q.sync_status, q.payload_json
                FROM tbt_count_history h
                INNER JOIN tb_sync_queue q
                        ON q.source_table='tbt_count_history'
                       AND q.source_id=h.history_id
                       AND q.sync_type='AUDIT'
                WHERE h.history_id IN ({placeholders})
                  AND COALESCE(h.is_audit,0)=1
                """,
                ids,
            ).fetchall()
            if len(rows) != len(ids):
                raise ValueError("พบบางรายการ Audit ไม่ครบหรือไม่มี Queue เดิม")

            location = cursor.execute(
                """
                SELECT location_code FROM tb_location
                WHERE plan_id=? AND CAST(location_id AS TEXT)=CAST(? AS TEXT)
                LIMIT 1
                """,
                (rows[0]["plan_id"], new_location_id),
            ).fetchone()
            if not location:
                raise ValueError("ไม่พบ Location ใหม่")

            for row in rows:
                status = str(row["sync_status"] or "PENDING").upper()
                if status in ("SYNCING", "SYNCED"):
                    raise ValueError("มีรายการกำลัง Sync หรือ Sync แล้ว ไม่สามารถแก้ไขได้")

            updated_details = set()
            for row in rows:
                payload = json.loads(row["payload_json"] or "{}")
                payload.update({
                    "history_id": int(row["history_id"]),
                    "transaction_guid": str(row["transaction_guid"]),
                    "reference_transaction_guid": None,
                    "transaction_type": "AUDIT",
                    "operation_type": "INSERT",
                    "location_id": new_location_id,
                    "location_code": location["location_code"],
                    "checker": auditor,
                    "auditor": auditor,
                    "is_audit": 1,
                    "audit_round": int(row["audit_round"] or 1),
                    "modified_at": now,
                })
                payload.pop("correction_type", None)

                cursor.execute(
                    """
                    UPDATE tbt_count_history
                    SET reference_transaction_guid=NULL,
                        operation_type='INSERT',
                        location_id=?, checker=?
                    WHERE history_id=?
                    """,
                    (new_location_id, auditor, row["history_id"]),
                )
                cursor.execute(
                    """
                    UPDATE tb_sync_queue
                    SET payload_json=?, sync_status='PENDING', retry_count=0,
                        error_message=NULL
                    WHERE queue_id=?
                    """,
                    (json.dumps(payload, ensure_ascii=False), row["queue_id"]),
                )
                if row["plan_detail_id"] not in updated_details:
                    cursor.execute(
                        """
                        UPDATE tb_plan_detail
                        SET location_id=?, new_location=?, is_change_location=1,
                            auditor=?, audit_sync_status='PENDING',
                            audit_transaction_guid=?, audit_modified_at=?,
                            local_is_changed=1, local_sync_status='PENDING',
                            local_updated_at=?
                        WHERE plan_detail_id=?
                        """,
                        (new_location_id, location["location_code"], auditor,
                         row["transaction_guid"], now, now, row["plan_detail_id"]),
                    )
                    updated_details.add(row["plan_detail_id"])

            connection.commit()
            return {"success": True, "updated": len(rows)}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()

