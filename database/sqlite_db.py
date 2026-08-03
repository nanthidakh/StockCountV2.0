"""
=========================================================
Project : HWK_StockV1
File    : database/sqlite_db.py

SQLite Database Manager
Python 3.11
=========================================================
"""

import os
import sqlite3

from utils.logger import logger


class SQLiteDB:

    def __init__(
        self,
        db_path
    ):
        self.db_path = db_path
        self.conn = None

    # =====================================================
    # Prepare Folder
    # =====================================================

    def _prepare_folder(
        self
    ):
        folder = os.path.dirname(
            self.db_path
        )

        if folder and not os.path.exists(folder):
            os.makedirs(
                folder,
                exist_ok=True
            )

    # =====================================================
    # Create Connection
    # =====================================================

    def _create_connection(
        self
    ):
        self._prepare_folder()

        connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA busy_timeout = 30000"
        )

        connection.execute(
            "PRAGMA journal_mode = WAL"
        )

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

    # =====================================================
    # Connect
    # =====================================================

    def connect(
        self
    ):
        """
        Connection หลักของ Application
        """

        if self.conn is not None:
            return self.conn

        self.conn = self._create_connection()

        logger.info(
            "SQLite Connected"
        )

        return self.conn

    # =====================================================
    # Get Separate Connection
    # =====================================================

    def get_connection(
        self
    ):
        """
        สร้าง Connection ใหม่ทุกครั้ง

        ใช้สำหรับ:
        - Background Thread
        - DownloadRepository
        - Transaction ที่ต้องแยกจาก Connection หลัก

        ผู้เรียกต้อง close() Connection นี้เมื่อใช้งานเสร็จ
        """

        connection = self._create_connection()

        logger.info(
            "SQLite Worker Connection Created"
        )

        return connection

    # =====================================================
    # Check Connection
    # =====================================================

    def _ensure_connected(
        self
    ):
        if self.conn is None:
            self.connect()

    # =====================================================
    # Execute
    # =====================================================

    def execute(
        self,
        sql,
        params=()
    ):
        self._ensure_connected()

        cursor = self.conn.cursor()

        try:
            cursor.execute(
                sql,
                params
            )

            self.conn.commit()

            return cursor.lastrowid

        except Exception as e:
            self.conn.rollback()

            logger.error(
                str(e)
            )

            raise

        finally:
            cursor.close()

    # =====================================================
    # Begin Transaction
    # =====================================================

    def begin(
        self
    ):
        self._ensure_connected()

        self.conn.execute(
            "BEGIN"
        )

    # =====================================================
    # Query One
    # =====================================================

    def query_one(
        self,
        sql,
        params=()
    ):
        self._ensure_connected()

        cursor = self.conn.cursor()

        try:
            cursor.execute(
                sql,
                params
            )

            row = cursor.fetchone()

            if row:
                return dict(row)

            return None

        finally:
            cursor.close()

    # =====================================================
    # Query All
    # =====================================================

    def query_all(
        self,
        sql,
        params=()
    ):
        self._ensure_connected()

        cursor = self.conn.cursor()

        try:
            cursor.execute(
                sql,
                params
            )

            rows = cursor.fetchall()

            return [
                dict(row)
                for row in rows
            ]

        finally:
            cursor.close()

    # =====================================================
    # Repository Aliases
    # =====================================================

    def fetchone(
        self,
        sql,
        params=()
    ):
        return self.query_one(
            sql,
            params
        )

    def fetchall(
        self,
        sql,
        params=()
    ):
        return self.query_all(
            sql,
            params
        )

    # =====================================================
    # Commit
    # =====================================================

    def commit(
        self
    ):
        if self.conn:
            self.conn.commit()

    # =====================================================
    # Rollback
    # =====================================================

    def rollback(
        self
    ):
        if self.conn:
            self.conn.rollback()

    # =====================================================
    # Close Database
    # =====================================================

    def close(
        self
    ):
        if self.conn:
            self.conn.close()

            logger.info(
                "SQLite Closed"
            )

            self.conn = None