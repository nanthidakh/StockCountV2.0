"""
=========================================================
Project : HWK_StockV1
File    : repository/sync_repository.py

Android Sync Repository with per-send Batch GUID
=========================================================
"""

import json
import uuid
from datetime import datetime


class SyncRepository:
    LOCAL_PENDING = "PENDING"
    LOCAL_SYNCING = "SYNCING"
    LOCAL_SYNCED = "SYNCED"
    LOCAL_ERROR = "ERROR"

    def __init__(self, db):
        self.db = db
        self.ensure_schema()

    def ensure_schema(self):
        connection = self.db.get_connection()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_config
                (
                    config_key TEXT PRIMARY KEY,
                    config_value TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(tb_sync_queue)")
            }
            additions = {
                "transaction_type": "TEXT",
                "source_table": "TEXT",
                "source_id": "INTEGER",
                "last_attempt_at": "TEXT",
                "synced_at": "TEXT",
                "created_at": "TEXT",
                "sync_batch_guid": "TEXT",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE tb_sync_queue ADD COLUMN {name} {definition}"
                    )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_sync_queue_plan_status
                ON tb_sync_queue(plan_id, sync_status, queue_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_sync_queue_batch
                ON tb_sync_queue(plan_id, sync_batch_guid, queue_id)
                """
            )
            connection.commit()
        finally:
            connection.close()

    def get_or_create_device_id(self):
        connection = self.db.get_connection()
        try:
            row = connection.execute(
                "SELECT config_value FROM app_config WHERE config_key='device_id'"
            ).fetchone()
            if row and str(row["config_value"] or "").strip():
                return str(row["config_value"]).strip()
            device_id = str(uuid.uuid4())
            connection.execute(
                "INSERT OR REPLACE INTO app_config(config_key, config_value) VALUES('device_id', ?)",
                (device_id,),
            )
            connection.commit()
            return device_id
        finally:
            connection.close()

    def create_batch_guid(self, plan_id, transaction_type="COUNT"):
        batch_guid = str(uuid.uuid4())
        self.set_current_batch_guid(plan_id, batch_guid, transaction_type)
        return batch_guid

    def set_current_batch_guid(self, plan_id, batch_guid, transaction_type="COUNT"):
        key = f"sync_batch_guid_plan_{int(plan_id)}_{str(transaction_type).upper()}"
        connection = self.db.get_connection()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO app_config(config_key, config_value) VALUES(?, ?)",
                (key, str(batch_guid or "")),
            )
            connection.commit()
        finally:
            connection.close()

    def get_current_batch_guid(self, plan_id, transaction_type="COUNT"):
        key = f"sync_batch_guid_plan_{int(plan_id)}_{str(transaction_type).upper()}"
        connection = self.db.get_connection()
        try:
            row = connection.execute(
                "SELECT config_value FROM app_config WHERE config_key=?",
                (key,),
            ).fetchone()
            return str(row["config_value"] or "").strip() if row else ""
        finally:
            connection.close()

    def get_local_summary(self, plan_id, transaction_type="COUNT"):
        totals = {
            self.LOCAL_PENDING: 0,
            self.LOCAL_SYNCING: 0,
            self.LOCAL_SYNCED: 0,
            self.LOCAL_ERROR: 0,
        }
        connection = self.db.get_connection()
        try:
            rows = connection.execute(
                """
                SELECT UPPER(COALESCE(sync_status, 'PENDING')) AS sync_status,
                       COUNT(*) AS total
                FROM tb_sync_queue
                WHERE plan_id = ?
                  AND UPPER(COALESCE(transaction_type, sync_type, 'COUNT')) = ?
                GROUP BY UPPER(COALESCE(sync_status, 'PENDING'))
                """,
                (int(plan_id), str(transaction_type).upper()),
            ).fetchall()
            for row in rows:
                status = str(row["sync_status"] or "").upper()
                if status in totals:
                    totals[status] = int(row["total"] or 0)
            return totals
        finally:
            connection.close()

    def get_sendable(self, plan_id, limit=500, include_error=False, transaction_type="COUNT"):
        statuses = [self.LOCAL_PENDING]
        if include_error:
            statuses.append(self.LOCAL_ERROR)
        marks = ",".join("?" for _ in statuses)
        connection = self.db.get_connection()
        try:
            rows = connection.execute(
                f"""
                SELECT *
                FROM tb_sync_queue
                WHERE plan_id = ?
                  AND UPPER(COALESCE(sync_status, 'PENDING')) IN ({marks})
                   AND UPPER(COALESCE(transaction_type, sync_type, 'COUNT')) = ?
                  AND COALESCE(retry_count, 0) < 5
                ORDER BY queue_id
                LIMIT ?
                """,
                (int(plan_id), *statuses, str(transaction_type).upper(), int(limit)),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def assign_batch(self, guids, batch_guid):
        if not guids:
            return
        connection = self.db.get_connection()
        try:
            marks = ",".join("?" for _ in guids)
            connection.execute(
                f"""
                UPDATE tb_sync_queue
                SET sync_batch_guid=?
                WHERE transaction_guid IN ({marks})
                """,
                (str(batch_guid), *[str(x) for x in guids]),
            )
            connection.commit()
        finally:
            connection.close()

    def mark_syncing(self, guids):
        self._update_many(
            guids,
            "sync_status='SYNCING', last_attempt_at=?, error_message=NULL",
            (self._now(),),
        )

    def mark_synced(self, transaction_guid):
        connection = self.db.get_connection()
        try:
            now = self._now()
            connection.execute(
                """
                UPDATE tb_sync_queue
                SET sync_status='SYNCED', sync_date=?, synced_at=?, error_message=NULL
                WHERE transaction_guid=?
                """,
                (now, now, str(transaction_guid)),
            )
            self._refresh_detail_status(connection, transaction_guid)
            connection.commit()
        finally:
            connection.close()

    def mark_error(self, transaction_guid, message):
        connection = self.db.get_connection()
        try:
            connection.execute(
                """
                UPDATE tb_sync_queue
                SET sync_status='ERROR',
                    retry_count=COALESCE(retry_count,0)+1,
                    error_message=?, last_attempt_at=?
                WHERE transaction_guid=?
                """,
                (str(message or "Unknown error")[:1000], self._now(), str(transaction_guid)),
            )
            self._refresh_detail_status(connection, transaction_guid)
            connection.commit()
        finally:
            connection.close()

    def restore_pending(self, guids, message=None):
        if not guids:
            return
        connection = self.db.get_connection()
        try:
            marks = ",".join("?" for _ in guids)
            connection.execute(
                f"""
                UPDATE tb_sync_queue
                SET sync_status='PENDING', error_message=?
                WHERE transaction_guid IN ({marks})
                  AND sync_status='SYNCING'
                """,
                (message, *[str(x) for x in guids]),
            )
            connection.commit()
        finally:
            connection.close()

    def build_transaction(self, queue_row):
        payload = json.loads(queue_row.get("payload_json") or "{}")
        queue_type = str(
            queue_row.get("transaction_type")
            or queue_row.get("sync_type")
            or payload.get("transaction_type")
            or "COUNT"
        ).upper()

        transaction_type = "AUDIT" if queue_type == "AUDIT" else "COUNT"
        operation_type = "INSERT"
        if queue_type == "CORRECTION_QTY":
            operation_type = "UPDATE_QTY"
        elif queue_type == "CORRECTION_LOCATION":
            operation_type = "UPDATE_LOCATION"
        elif str(payload.get("operation_type") or "").upper() in (
            "INSERT", "UPDATE_QTY", "UPDATE_LOCATION"
        ):
            operation_type = str(payload["operation_type"]).upper()

        reference_guid = payload.get("reference_transaction_guid")
        if not reference_guid and operation_type != "INSERT":
            reference_guid = self._find_history_guid(
                payload.get("history_id") or queue_row.get("source_id")
            )

        location_id = payload.get("location_id")
        try:
            location_id = int(location_id) if location_id not in (None, "") else None
        except (TypeError, ValueError):
            location_id = None

        transaction_date = (
            payload.get("transaction_date")
            or payload.get("check_date")
            or payload.get("audit_date")
            or payload.get("modified_at")
            or payload.get("create_date")
            or queue_row.get("create_date")
            or queue_row.get("created_at")
        )

        qty_value = (
            payload.get("qty_audit")
            if transaction_type == "AUDIT"
            else payload.get("qty", payload.get("qty_on_hand", 0))
        )

        return {
            "transaction_guid": str(queue_row.get("transaction_guid") or payload.get("transaction_guid") or ""),
            "reference_transaction_guid": reference_guid,
            "transaction_no": f"Q{queue_row.get('queue_id', 0)}",
            "transaction_type": transaction_type,
            "operation_type": operation_type,
            "plan_id": int(payload.get("plan_id") or queue_row.get("plan_id") or 0),
            "plan_detail_id": int(payload.get("plan_detail_id") or queue_row.get("plan_detail_id") or 0),
            "item_id": int(payload.get("item_id") or 0),
            "location_id": location_id,
            "location_code": payload.get("location_code"),
            "barcode": payload.get("barcode"),
            "qty": float(qty_value or 0),
            "checker": payload.get("auditor") or payload.get("checker") or "ANDROID",
            "audit_round": int(payload.get("audit_round") or 0),
            "transaction_date": transaction_date,
        }

    def _find_history_guid(self, history_id):
        if history_id in (None, ""):
            return None
        connection = self.db.get_connection()
        try:
            row = connection.execute(
                "SELECT transaction_guid FROM tbt_count_history WHERE history_id=?",
                (int(history_id),),
            ).fetchone()
            return str(row["transaction_guid"]) if row else None
        finally:
            connection.close()

    def _refresh_detail_status(self, connection, transaction_guid):
        row = connection.execute(
            "SELECT plan_detail_id, UPPER(COALESCE(transaction_type,sync_type,'COUNT')) AS transaction_type "
            "FROM tb_sync_queue WHERE transaction_guid=?",
            (str(transaction_guid),),
        ).fetchone()
        if not row or row["plan_detail_id"] is None:
            return
        detail_id = int(row["plan_detail_id"])
        tx_type = str(row["transaction_type"] or "COUNT").upper()
        pending = connection.execute(
            """
            SELECT COUNT(*) AS total FROM tb_sync_queue
            WHERE plan_detail_id=?
              AND UPPER(COALESCE(transaction_type,sync_type,'COUNT'))=?
              AND UPPER(sync_status) IN ('PENDING','SYNCING','ERROR')
            """,
            (detail_id, tx_type),
        ).fetchone()["total"]
        status = "PENDING" if int(pending or 0) > 0 else "SYNCED"
        columns = {r["name"] for r in connection.execute("PRAGMA table_info(tb_plan_detail)")}
        assignments, values = [], []
        target = "audit_sync_status" if tx_type == "AUDIT" else "count_sync_status"
        if target in columns:
            assignments.append(f"{target}=?")
            values.append(status)
        if "local_sync_status" in columns:
            assignments.append("local_sync_status=?")
            values.append(status)
        if assignments:
            values.append(detail_id)
            connection.execute(
                f"UPDATE tb_plan_detail SET {', '.join(assignments)} WHERE plan_detail_id=?",
                tuple(values),
            )

    def _update_many(self, guids, set_sql, prefix_values=()):
        if not guids:
            return
        connection = self.db.get_connection()
        try:
            marks = ",".join("?" for _ in guids)
            connection.execute(
                f"UPDATE tb_sync_queue SET {set_sql} WHERE transaction_guid IN ({marks})",
                (*prefix_values, *[str(x) for x in guids]),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")
