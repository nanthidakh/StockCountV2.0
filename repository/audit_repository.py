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
            WHERE pd.plan_id=? AND pd.item_id=?
              AND (
                    CAST(pd.location_id AS TEXT)=CAST(? AS TEXT)
                 OR TRIM(COALESCE(NULLIF(pd.new_location,''),pd.before_location))=TRIM(COALESCE(l.location_code,''))
              )
            LIMIT 1
        """, (location_id, int(plan_id), int(item_id), location_id))

    def find_duplicate(self, plan_id, item_id, location_id, audit_round):
        return self.db.query_one("""
            SELECT h.*, i.item_code, i.item_name, i.uom,
                   COALESCE(l.location_code,CAST(h.location_id AS TEXT)) AS location_code
            FROM tbt_count_history h
            JOIN tb_item i ON i.item_id=h.item_id
            LEFT JOIN tb_location l ON l.plan_id=h.plan_id
                 AND CAST(l.location_id AS TEXT)=CAST(h.location_id AS TEXT)
            WHERE h.plan_id=? AND h.item_id=?
              AND CAST(h.location_id AS TEXT)=CAST(? AS TEXT)
              AND COALESCE(h.is_audit,0)=1
              AND COALESCE(h.audit_round,0)=?
            ORDER BY h.history_id DESC LIMIT 1
        """, (int(plan_id), int(item_id), str(location_id), int(audit_round)))

    def save_audit(self, transaction: CountTransaction, duplicate_mode="ADD"):
        if transaction.transaction_type != TransactionType.AUDIT:
            raise ValueError("Transaction ต้องเป็น AUDIT")
        if transaction.audit_round <= 0:
            raise ValueError("Audit Round ต้องมากกว่า 0")

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            detail = cursor.execute("""
                SELECT * FROM tb_plan_detail
                WHERE plan_detail_id=? AND plan_id=? AND item_id=? LIMIT 1
            """, (transaction.plan_detail_id, transaction.plan_id, transaction.item_id)).fetchone()
            if detail is None:
                raise ValueError("ไม่พบรายการ Audit ในใบงาน")

            old = cursor.execute("""
                SELECT history_id, transaction_guid, qty
                FROM tbt_count_history
                WHERE plan_id=? AND item_id=? AND CAST(location_id AS TEXT)=CAST(? AS TEXT)
                  AND COALESCE(is_audit,0)=1 AND COALESCE(audit_round,0)=?
                ORDER BY history_id DESC LIMIT 1
            """, (transaction.plan_id, transaction.item_id, transaction.location_id,
                  transaction.audit_round)).fetchone()

            mode = str(duplicate_mode or "ADD").upper()
            if old and mode == "CANCEL":
                return {"success": False, "cancelled": True}

            qty_to_save = transaction.qty
            operation = OperationType.INSERT
            reference_guid = None
            if old and mode == "ADD":
                qty_to_save = float(old["qty"] or 0) + transaction.qty
                operation = OperationType.UPDATE_QTY
                reference_guid = old["transaction_guid"]
            elif old and mode == "REPLACE":
                operation = OperationType.UPDATE_QTY
                reference_guid = old["transaction_guid"]

            transaction.qty = qty_to_save
            transaction.operation_type = operation
            transaction.reference_transaction_guid = reference_guid

            cursor.execute("""
                UPDATE tb_plan_detail
                SET qty_audit=?, auditor=?, audit_date=?, audit_round=?,
                    audit_sync_status='PENDING', audit_transaction_guid=?,
                    audit_modified_at=?, local_is_changed=1,
                    local_sync_status='PENDING', local_updated_at=?
                WHERE plan_detail_id=?
            """, (
                transaction.qty, transaction.checker, transaction.create_date,
                transaction.audit_round, transaction.transaction_guid,
                transaction.create_date, transaction.create_date,
                transaction.plan_detail_id,
            ))

            cursor.execute("""
                INSERT INTO tbt_count_history
                (transaction_guid,reference_transaction_guid,operation_type,
                 plan_id,plan_detail_id,item_id,location_id,barcode,qty,checker,
                 is_audit,audit_round,create_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)
            """, (
                transaction.transaction_guid, transaction.reference_transaction_guid,
                transaction.operation_type.value, transaction.plan_id,
                transaction.plan_detail_id, transaction.item_id,
                transaction.location_id, transaction.barcode, transaction.qty,
                transaction.checker, transaction.audit_round, transaction.create_date,
            ))
            history_id = cursor.lastrowid

            location = cursor.execute("""
                SELECT location_code FROM tb_location
                WHERE plan_id=? AND CAST(location_id AS TEXT)=CAST(? AS TEXT) LIMIT 1
            """, (transaction.plan_id, transaction.location_id)).fetchone()
            payload = transaction.to_dict()
            payload["history_id"] = history_id
            payload["location_code"] = location["location_code"] if location else None

            cursor.execute("""
                INSERT INTO tb_sync_queue
                (plan_id,plan_detail_id,transaction_guid,sync_type,transaction_type,
                 source_table,source_id,payload_json,sync_status,retry_count,create_date,created_at)
                VALUES (?,?,?,'AUDIT','AUDIT','tbt_count_history',?,?,'PENDING',0,?,?)
            """, (
                transaction.plan_id, transaction.plan_detail_id,
                transaction.transaction_guid, history_id,
                json.dumps(payload, ensure_ascii=False),
                transaction.create_date, transaction.create_date,
            ))
            connection.commit()
            return {
                "success": True,
                "history_id": history_id,
                "transaction_guid": transaction.transaction_guid,
                "qty_audit": transaction.qty,
                "operation_type": transaction.operation_type.value,
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
                   COALESCE(l.location_code,CAST(h.location_id AS TEXT)) AS location_code
            FROM tbt_count_history h
            JOIN tb_item i ON i.item_id=h.item_id
            LEFT JOIN tb_location l ON l.plan_id=h.plan_id
              AND CAST(l.location_id AS TEXT)=CAST(h.location_id AS TEXT)
            WHERE h.plan_id=? AND COALESCE(h.is_audit,0)=1
            ORDER BY h.history_id DESC LIMIT ?
        """, (int(plan_id), int(limit)))

    def correct_qty(self, history_id, new_qty, auditor):
        source = self._history(history_id)
        tx = CountTransaction(
            transaction_guid=str(__import__('uuid').uuid4()),
            plan_id=int(source["plan_id"]), plan_detail_id=int(source["plan_detail_id"]),
            item_id=int(source["item_id"]), location_id=str(source["location_id"]),
            barcode=str(source.get("barcode") or ""), qty=float(new_qty), checker=auditor,
            create_date=datetime.now().isoformat(timespec="seconds"),
            transaction_type=TransactionType.AUDIT,
            operation_type=OperationType.UPDATE_QTY,
            audit_round=int(source.get("audit_round") or 1),
            reference_transaction_guid=str(source["transaction_guid"]),
        )
        return self.save_audit(tx, duplicate_mode="REPLACE")

    def correct_locations(self, history_ids, new_location_id, auditor):
        updated = 0
        for history_id in history_ids:
            source = self._history(history_id)
            tx = CountTransaction(
                transaction_guid=str(__import__('uuid').uuid4()),
                plan_id=int(source["plan_id"]), plan_detail_id=int(source["plan_detail_id"]),
                item_id=int(source["item_id"]), location_id=str(new_location_id),
                barcode=str(source.get("barcode") or ""), qty=float(source["qty"]), checker=auditor,
                create_date=datetime.now().isoformat(timespec="seconds"),
                transaction_type=TransactionType.AUDIT,
                operation_type=OperationType.UPDATE_LOCATION,
                audit_round=int(source.get("audit_round") or 1),
                reference_transaction_guid=str(source["transaction_guid"]),
            )
            self._save_location_correction(tx)
            updated += 1
        return {"success": True, "updated": updated}

    def _history(self, history_id):
        row = self.db.query_one("SELECT * FROM tbt_count_history WHERE history_id=? AND is_audit=1", (int(history_id),))
        if not row:
            raise ValueError("ไม่พบรายการ Audit ต้นทาง")
        return row

    def _save_location_correction(self, tx):
        connection = self.db.get_connection(); cursor = connection.cursor()
        try:
            connection.execute("BEGIN IMMEDIATE")
            location = cursor.execute("SELECT location_code FROM tb_location WHERE plan_id=? AND CAST(location_id AS TEXT)=CAST(? AS TEXT)", (tx.plan_id,tx.location_id)).fetchone()
            if not location: raise ValueError("ไม่พบ Location ใหม่")
            cursor.execute("""
                INSERT INTO tbt_count_history
                (transaction_guid,reference_transaction_guid,operation_type,plan_id,plan_detail_id,item_id,location_id,barcode,qty,checker,is_audit,audit_round,create_date)
                VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)
            """, (tx.transaction_guid,tx.reference_transaction_guid,tx.operation_type.value,tx.plan_id,tx.plan_detail_id,tx.item_id,tx.location_id,tx.barcode,tx.qty,tx.checker,tx.audit_round,tx.create_date))
            hid=cursor.lastrowid; payload=tx.to_dict(); payload.update({"history_id":hid,"location_code":location["location_code"]})
            cursor.execute("""
                INSERT INTO tb_sync_queue(plan_id,plan_detail_id,transaction_guid,sync_type,transaction_type,source_table,source_id,payload_json,sync_status,retry_count,create_date,created_at)
                VALUES(?,?,?,'AUDIT','AUDIT','tbt_count_history',?,?,'PENDING',0,?,?)
            """,(tx.plan_id,tx.plan_detail_id,tx.transaction_guid,hid,json.dumps(payload,ensure_ascii=False),tx.create_date,tx.create_date))
            connection.commit()
        except Exception:
            connection.rollback(); raise
        finally:
            cursor.close(); connection.close()
