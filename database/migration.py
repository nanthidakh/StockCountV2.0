"""
=========================================================
Project : HWK_StockV1
File    : database/migration.py

SQLite Database Migration

=========================================================
"""


from utils.logger import logger



class DatabaseMigration:


    CURRENT_VERSION = 1



    def __init__(
        self,
        db
    ):

        self.db = db





    # =====================================================
    # Run Migration
    # =====================================================


    def run(
        self
    ):


        self.create_version_table()



        current = self.get_version()



        logger.info(

            f"Database Version : {current}"

        )



        while current < self.CURRENT_VERSION:



            next_version = current + 1



            self.apply_migration(

                next_version

            )



            self.set_version(

                next_version

            )



            current = next_version





    # =====================================================
    # Version Table
    # =====================================================


    def create_version_table(
        self
    ):


        self.db.execute(

        """

        CREATE TABLE IF NOT EXISTS tb_database_version

        (

            version INTEGER

        )


        """

        )



        result = self.db.query_one(

        """

        SELECT COUNT(*) AS cnt

        FROM tb_database_version


        """

        )



        if result["cnt"] == 0:


            self.db.execute(

            """

            INSERT INTO tb_database_version

            VALUES(0)


            """

            )





    # =====================================================
    # Get Version
    # =====================================================


    def get_version(
        self
    ):


        result = self.db.query_one(

        """

        SELECT version

        FROM tb_database_version


        """

        )


        return result["version"]





    # =====================================================
    # Set Version
    # =====================================================


    def set_version(
        self,
        version
    ):


        self.db.execute(

        """

        UPDATE tb_database_version

        SET version = ?


        """,

        (

            version,

        )

        )





    # =====================================================
    # Migration Router
    # =====================================================


    def apply_migration(
        self,
        version
    ):


        if version == 1:


            self.version_1()



        elif version == 2:


            self.version_2()



        elif version == 3:


            self.version_3()





    # =====================================================
    # Version 1
    # =====================================================


    def version_1(
        self
    ):


        """
        Initial Database


        Schema created separately


        """

        logger.info(

            "Migration Version 1"

        )





    # =====================================================
    # Version 2 Example
    # =====================================================


    def version_2(
        self
    ):


        """
        Example:

        Add new column


        """


        self.db.execute(

        """

        ALTER TABLE tbt_count_history

        ADD COLUMN remark TEXT


        """

        )





    # =====================================================
    # Version 3 Example
    # =====================================================


    def version_3(
        self
    ):


        """
        Example:

        Add new table


        """


        self.db.execute(

        """

        CREATE TABLE IF NOT EXISTS tb_sync_log

        (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            message TEXT,

            create_date TEXT

        )


        """

        )