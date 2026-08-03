"""
=========================================================
Project : HWK_StockV1
File    : database/schema.py

SQLite Schema
=========================================================
"""


def create_tables(db):

    sql_list = [

        # =====================================================
        # Application Config
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS app_config
        (
            config_key TEXT PRIMARY KEY,
            config_value TEXT
        )
        """,

        # =====================================================
        # Plan Header
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_plan
        (
            plan_id INTEGER PRIMARY KEY,
            plan_name TEXT,
            status TEXT,
            download_status INTEGER DEFAULT 0,
            download_date TEXT
        )
        """,

        # =====================================================
        # Plan Detail
        # Latest state of Count and Audit
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_plan_detail
        (
            plan_detail_id INTEGER PRIMARY KEY,
            plan_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            source_item_id INTEGER,
            location_id TEXT,

            qty REAL DEFAULT 0,

            qty_on_hand REAL DEFAULT 0,
            checker TEXT,
            check_date TEXT,
            count_sync_status TEXT,
            count_transaction_guid TEXT,
            count_modified_at TEXT,

            qty_audit REAL DEFAULT 0,
            auditor TEXT,
            audit_date TEXT,
            audit_round INTEGER DEFAULT 0,
            audit_sync_status TEXT,
            audit_transaction_guid TEXT,
            audit_modified_at TEXT,

            is_check INTEGER DEFAULT 0,

            server_status TEXT,
            audit_round_required INTEGER DEFAULT 0,
            difference_qty REAL DEFAULT 0,

            FOREIGN KEY (plan_id)
                REFERENCES tb_plan(plan_id),

            FOREIGN KEY (item_id)
                REFERENCES tb_item(item_id),

            FOREIGN KEY (location_id)
                REFERENCES tb_location(location_id)
        )
        """,

        # =====================================================
        # Item Master
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_item
        (
            item_id INTEGER PRIMARY KEY,
            item_code TEXT,
            item_name TEXT,
            unit_name TEXT
        )
        """,

        # =====================================================
        # Barcode Master
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_barcode
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            barcode TEXT NOT NULL,

            FOREIGN KEY (item_id)
                REFERENCES tb_item(item_id)
        )
        """,

        # =====================================================
        # Location Master
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_location
        (
            location_id TEXT PRIMARY KEY,
            location_name TEXT
        )
        """,

        # =====================================================
        # Count History
        # Append Only
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tbt_count_history
        (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_guid TEXT NOT NULL,
            reference_transaction_guid TEXT,
            operation_type TEXT NOT NULL DEFAULT 'INSERT',
            plan_id INTEGER NOT NULL,
            plan_detail_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            location_id TEXT,
            barcode TEXT,
            qty REAL NOT NULL,
            checker TEXT,
            is_audit INTEGER DEFAULT 0,
            audit_round INTEGER NOT NULL DEFAULT 0,
            create_date TEXT NOT NULL
        )
        """,

        # =====================================================
        # Legacy Audit History (unused; kept for old-device compatibility)
        # New Audit data uses tbt_count_history is_audit=1
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_audit_history
        (
            audit_history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_guid TEXT NOT NULL,
            reference_transaction_guid TEXT,
            operation_type TEXT NOT NULL DEFAULT 'INSERT',
            plan_id INTEGER NOT NULL,
            plan_detail_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            location_id TEXT,
            barcode TEXT,
            qty_audit REAL NOT NULL,
            auditor TEXT,
            audit_round INTEGER NOT NULL,
            create_date TEXT NOT NULL
        )
        """,

        # =====================================================
        # Offline Sync Queue
        # =====================================================
        """
        CREATE TABLE IF NOT EXISTS tb_sync_queue
        (
            queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            plan_detail_id INTEGER NOT NULL,
            transaction_guid TEXT NOT NULL,
            sync_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            create_date TEXT NOT NULL,
            sync_date TEXT
        )
        """,

        # =====================================================
        # Indexes
        # =====================================================
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_barcode_barcode
        ON tb_barcode(barcode)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            ix_plan_detail_plan_location
        ON tb_plan_detail(plan_id, location_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            ix_plan_detail_plan_item
        ON tb_plan_detail(plan_id, item_id)
        """,

        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_sync_queue_transaction
        ON tb_sync_queue(sync_type, transaction_guid)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            ix_sync_queue_status
        ON tb_sync_queue(sync_status, sync_type)
        """
    ]

    for sql in sql_list:
        db.execute(sql)