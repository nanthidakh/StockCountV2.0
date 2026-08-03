"""
=========================================================
Project : HWK_StockV1
File    : repository/base_repository.py

Base Repository

=========================================================
"""


from utils.logger import logger





class BaseRepository:



    def __init__(
        self,
        db
    ):


        self.db = db





    # =====================================================
    # Insert
    # =====================================================


    def insert(
        self,
        table,
        data
    ):


        try:


            columns = ",".join(

                data.keys()

            )


            placeholders = ",".join(

                [

                    "?"

                    for _ in data

                ]

            )


            sql = f"""

            INSERT INTO {table}

            (

                {columns}

            )

            VALUES

            (

                {placeholders}

            )

            """



            return self.db.execute(

                sql,

                tuple(data.values())

            )



        except Exception as e:


            logger.error(

                f"Insert Error {table}: {e}"

            )


            raise e





    # =====================================================
    # Update
    # =====================================================


    def update(
        self,
        table,
        data,
        where,
        params
    ):


        try:


            set_value = ",".join(

                [

                    f"{k}=?"

                    for k in data.keys()

                ]

            )



            sql = f"""

            UPDATE {table}

            SET

            {set_value}


            WHERE

            {where}

            """



            return self.db.execute(

                sql,

                tuple(data.values())

                +

                tuple(params)

            )



        except Exception as e:


            logger.error(

                f"Update Error {table}: {e}"

            )


            raise e





    # =====================================================
    # Delete
    # =====================================================


    def delete(
        self,
        table,
        where,
        params
    ):


        sql = f"""

        DELETE FROM {table}

        WHERE {where}

        """



        return self.db.execute(

            sql,

            params

        )





    # =====================================================
    # Query One
    # =====================================================


    def find_one(
        self,
        sql,
        params=()
    ):


        return self.db.query_one(

            sql,

            params

        )





    # =====================================================
    # Query All
    # =====================================================


    def find_all(
        self,
        sql,
        params=()
    ):


        return self.db.query_all(

            sql,

            params

        )