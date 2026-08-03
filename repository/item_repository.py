"""
=========================================================
Project : HWK_StockV1
File    : repository/item_repository.py

Item Repository

=========================================================
"""


from repository.base_repository import BaseRepository





class ItemRepository(BaseRepository):


    def __init__(
        self,
        db
    ):

        super().__init__(db)



    # =====================================================
    # Save Item
    # =====================================================

    def save_item(
        self,
        item
    ):

        sql = """

        INSERT OR REPLACE INTO tb_item
        (
            item_id,
            item_code,
            item_name,
            unit_name
        )

        VALUES
        (
            ?,
            ?,
            ?,
            ?
        )

        """

        return self.db.execute(

            sql,

            (
                item.item_id,
                item.item_code,
                item.item_name,
                item.unit_name
            )

        )



    # =====================================================
    # Save Barcode
    # =====================================================

    def save_barcode(
        self,
        item_id,
        barcode
    ):

        sql = """

        INSERT INTO tb_barcode
        (
            item_id,
            barcode
        )

        VALUES
        (
            ?,
            ?
        )

        """

        return self.db.execute(

            sql,

            (
                item_id,
                barcode
            )

        )



    # =====================================================
    # Find Item By Barcode
    # =====================================================

    def find_by_barcode(
        self,
        barcode
    ):


        sql = """

        SELECT

            i.item_id,

            i.item_code,

            i.item_name,

            i.unit_name


        FROM tb_item i


        INNER JOIN tb_barcode b

            ON i.item_id = b.item_id


        WHERE

            b.barcode = ?


        LIMIT 1

        """



        return self.db.query_one(

            sql,

            (
                barcode,
            )

        )



    # =====================================================
    # Find Item By Code
    # =====================================================

    def find_by_code(
        self,
        item_code
    ):


        sql = """

        SELECT

            item_id,

            item_code,

            item_name,

            unit_name


        FROM tb_item


        WHERE

            item_code = ?


        LIMIT 1

        """



        return self.db.query_one(

            sql,

            (
                item_code,
            )

        )



    # =====================================================
    # Get All Items
    # =====================================================

    def get_all(
        self
    ):


        sql = """

        SELECT *

        FROM tb_item

        ORDER BY item_code

        """



        return self.db.query_all(

            sql

        )