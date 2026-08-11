"""SQLite schema for HWK Stock.

This module is the single source of truth for the HWK Stock database.
Repositories must not create, alter, or migrate tables.
"""

TABLES = (
    """
    CREATE TABLE IF NOT EXISTS app_config (
        config_key TEXT PRIMARY KEY,
        config_value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_plan (
        plan_id INTEGER PRIMARY KEY,
        plan_code TEXT NOT NULL,
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
        local_status TEXT NOT NULL DEFAULT 'DOWNLOADED'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_item (
        item_id INTEGER PRIMARY KEY,
        item_code TEXT NOT NULL,
        item_name TEXT,
        category TEXT,
        unit_rate REAL NOT NULL DEFAULT 0,
        qty REAL NOT NULL DEFAULT 0,
        uom TEXT,
        unit_cost REAL NOT NULL DEFAULT 0,
        batching_unit TEXT,
        batching_factor REAL NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        downloaded_at TEXT,
        updated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_barcode (
        barcode_id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        barcode TEXT NOT NULL,
        downloaded_at TEXT,
        UNIQUE (item_id, barcode),
        FOREIGN KEY (item_id) REFERENCES tb_item(item_id)
            ON UPDATE CASCADE ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_location (
        plan_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        location_code TEXT NOT NULL,
        location_name TEXT,
        downloaded_at TEXT,
        PRIMARY KEY (plan_id, location_id),
        UNIQUE (plan_id, location_code),
        FOREIGN KEY (plan_id) REFERENCES tb_plan(plan_id)
            ON UPDATE CASCADE ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_plan_detail (
        plan_detail_id INTEGER PRIMARY KEY,
        plan_id INTEGER NOT NULL,
        item_code TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        source_item_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        new_zone TEXT,
        before_zone TEXT,
        new_location TEXT,
        before_location TEXT,
        qty REAL NOT NULL DEFAULT 0,
        qty_on_hand REAL NOT NULL DEFAULT 0,
        qty_audit REAL NOT NULL DEFAULT 0,
        server_qty_audit REAL NOT NULL DEFAULT 0,
        check_date TEXT,
        checker TEXT,
        auditor TEXT,
        audit_user TEXT,
        audit_date TEXT,
        status_id INTEGER,
        remark TEXT,
        barcode TEXT,
        udf1 TEXT,
        udf2 TEXT,
        udf3 TEXT,
        audit_count INTEGER NOT NULL DEFAULT 0,
        audit_round INTEGER NOT NULL DEFAULT 0,
        create_date TEXT,
        create_by INTEGER,
        update_date TEXT,
        update_by INTEGER,
        server_updated_at TEXT,
        downloaded_at TEXT,
        is_confirm INTEGER NOT NULL DEFAULT 0,
        is_change_location INTEGER NOT NULL DEFAULT 0,
        is_check INTEGER NOT NULL DEFAULT 0,
        local_is_changed INTEGER NOT NULL DEFAULT 0,
        local_sync_status TEXT NOT NULL DEFAULT 'NONE',
        local_updated_at TEXT,
        count_sync_status TEXT NOT NULL DEFAULT 'NONE',
        count_modified_at TEXT,
        count_transaction_guid TEXT,
        audit_sync_status TEXT NOT NULL DEFAULT 'NONE',
        audit_transaction_guid TEXT,
        audit_modified_at TEXT,
        FOREIGN KEY (plan_id) REFERENCES tb_plan(plan_id)
            ON UPDATE CASCADE ON DELETE CASCADE,
        FOREIGN KEY (item_id) REFERENCES tb_item(item_id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (plan_id, location_id)
            REFERENCES tb_location(plan_id, location_id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tbt_count_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_guid TEXT NOT NULL UNIQUE,
        reference_transaction_guid TEXT,
        operation_type TEXT NOT NULL DEFAULT 'INSERT',
        plan_id INTEGER NOT NULL,
        plan_detail_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        location_id INTEGER,
        barcode TEXT,
        qty REAL NOT NULL,
        checker TEXT,
        is_audit INTEGER NOT NULL DEFAULT 0,
        audit_round INTEGER NOT NULL DEFAULT 0,
        create_date TEXT NOT NULL,
        FOREIGN KEY (plan_detail_id) REFERENCES tb_plan_detail(plan_detail_id),
        FOREIGN KEY (item_id) REFERENCES tb_item(item_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_audit_history (
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
        FOREIGN KEY (plan_detail_id) REFERENCES tb_plan_detail(plan_detail_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_sync_queue (
        queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_guid TEXT NOT NULL UNIQUE,
        plan_id INTEGER NOT NULL,
        plan_detail_id INTEGER,
        sync_type TEXT NOT NULL,
        transaction_type TEXT,
        source_table TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        payload_json TEXT,
        sync_status TEXT NOT NULL DEFAULT 'PENDING',
        retry_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        create_date TEXT,
        created_at TEXT NOT NULL,
        last_attempt_at TEXT,
        sync_date TEXT,
        synced_at TEXT,
        sync_batch_guid TEXT,
        FOREIGN KEY (plan_detail_id) REFERENCES tb_plan_detail(plan_detail_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tb_download_log (
        download_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER NOT NULL,
        download_date TEXT NOT NULL,
        status TEXT NOT NULL,
        item_count INTEGER NOT NULL DEFAULT 0,
        barcode_count INTEGER NOT NULL DEFAULT 0,
        location_count INTEGER NOT NULL DEFAULT 0,
        detail_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        FOREIGN KEY (plan_id) REFERENCES tb_plan(plan_id)
            ON UPDATE CASCADE ON DELETE CASCADE
    )
    """,
)

INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_tb_item_item_code ON tb_item(item_code)",
    "CREATE INDEX IF NOT EXISTS ix_tb_item_item_name ON tb_item(item_name)",
    "CREATE INDEX IF NOT EXISTS ix_tb_barcode_barcode ON tb_barcode(barcode)",
    "CREATE INDEX IF NOT EXISTS ix_tb_barcode_item_id ON tb_barcode(item_id)",
    "CREATE INDEX IF NOT EXISTS ix_tb_location_plan_code ON tb_location(plan_id, location_code)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_plan_item ON tb_plan_detail(plan_id, item_id)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_business_key ON tb_plan_detail(plan_id, item_code, location_id)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_location ON tb_plan_detail(plan_id, location_id)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_source_item ON tb_plan_detail(source_item_id)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_count_sync ON tb_plan_detail(plan_id, count_sync_status)",
    "CREATE INDEX IF NOT EXISTS ix_tb_plan_detail_audit_sync ON tb_plan_detail(plan_id, audit_sync_status)",
    "CREATE INDEX IF NOT EXISTS ix_count_history_plan_recent ON tbt_count_history(plan_id, history_id DESC)",
    "CREATE INDEX IF NOT EXISTS ix_audit_history_plan ON tb_audit_history(plan_id, audit_date)",
    "CREATE INDEX IF NOT EXISTS ix_sync_queue_plan_status ON tb_sync_queue(plan_id, sync_status, queue_id)",
    "CREATE INDEX IF NOT EXISTS ix_sync_queue_type_status ON tb_sync_queue(sync_type, sync_status, queue_id)",
    "CREATE INDEX IF NOT EXISTS ix_sync_queue_batch ON tb_sync_queue(plan_id, sync_batch_guid, queue_id)",
    "CREATE INDEX IF NOT EXISTS ix_download_log_plan ON tb_download_log(plan_id, download_log_id DESC)",
)


def create_tables(db) -> None:
    for sql in TABLES:
        db.execute(sql)
    for sql in INDEXES:
        db.execute(sql)
