"""
=========================================================
Project : HWK_StockV1
File    : database/init_db.py
Database Initializer
=========================================================
"""

from database.schema import create_tables
from repository.config_repository import ConfigRepository


def _column_names(db, table_name):
    rows = db.query_all(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in rows}


def _add_column(db, table_name, column_name, definition):
    if column_name not in _column_names(db, table_name):
        db.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def ensure_runtime_schema(db):
    """Upgrade older on-device databases without deleting local data."""
    # Columns used by CountRepository and current UI.
    _add_column(db, "tbt_count_history", "location_id", "TEXT")
    _add_column(db, "tbt_count_history", "reference_transaction_guid", "TEXT")
    _add_column(db, "tbt_count_history", "operation_type", "TEXT NOT NULL DEFAULT 'INSERT'")
    _add_column(db, "tbt_count_history", "audit_round", "INTEGER NOT NULL DEFAULT 0")

    detail_columns = {
        "source_item_id": "INTEGER",
        "local_is_changed": "INTEGER NOT NULL DEFAULT 0",
        "local_sync_status": "TEXT NOT NULL DEFAULT 'PENDING'",
        "local_updated_at": "TEXT",
        "count_sync_status": "TEXT NOT NULL DEFAULT 'NONE'",
        "count_modified_at": "TEXT",
        "count_transaction_guid": "TEXT",
        "qty_audit": "REAL NOT NULL DEFAULT 0",
        "auditor": "TEXT",
        "audit_date": "TEXT",
        "audit_count": "INTEGER NOT NULL DEFAULT 0",
        "audit_round": "INTEGER NOT NULL DEFAULT 0",
        "audit_sync_status": "TEXT NOT NULL DEFAULT 'NONE'",
        "audit_transaction_guid": "TEXT",
        "audit_modified_at": "TEXT",
    }
    for name, definition in detail_columns.items():
        _add_column(db, "tb_plan_detail", name, definition)

    queue_columns = {
        "plan_id": "INTEGER",
        "plan_detail_id": "INTEGER",
        "sync_type": "TEXT",
        "transaction_type": "TEXT",
        "source_table": "TEXT",
        "source_id": "INTEGER",
        "payload_json": "TEXT",
        "sync_status": "TEXT NOT NULL DEFAULT 'PENDING'",
        "retry_count": "INTEGER NOT NULL DEFAULT 0",
        "error_message": "TEXT",
        "create_date": "TEXT",
        "created_at": "TEXT",
        "sync_date": "TEXT",
        "last_attempt_at": "TEXT",
        "synced_at": "TEXT",
        "sync_batch_guid": "TEXT",
    }
    for name, definition in queue_columns.items():
        _add_column(db, "tb_sync_queue", name, definition)

    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_sync_queue_transaction_guid
        ON tb_sync_queue(transaction_guid)
        """
    )
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_count_history_plan_recent
        ON tbt_count_history(plan_id, history_id DESC)
        """
    )


def init_database(db):
    create_tables(db)
    ConfigRepository(db).create_table()
    ensure_runtime_schema(db)
