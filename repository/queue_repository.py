"""
=========================================================
Project : HWK_StockV1
File    : repository/queue_repository.py

Sync Queue Repository

=========================================================
"""


from repository.base_repository import BaseRepository



from models.sync_queue import SyncQueue, SyncStatus





class QueueRepository(
    BaseRepository
):



    # =====================================================
    # Insert Queue
    # =====================================================


    def save_queue(
        self,
        queue: SyncQueue
    ):


        return self.insert(

            "tb_sync_queue",

            {


                "transaction_guid":

                queue.transaction_guid,


                "transaction_type":

                queue.transaction_type,


                "payload_json":

                queue.payload_json,


                "sync_status":

                queue.sync_status,


                "retry_count":

                queue.retry_count,


                "error_message":

                queue.error_message,


                "create_date":

                queue.create_date,


                "sync_date":

                queue.sync_date


            }

        )





    # =====================================================
    # Get Waiting Queue
    # =====================================================


    def get_waiting(
        self,
        limit=500
    ):


        sql = """

        SELECT *

        FROM tb_sync_queue



        WHERE

        sync_status = ?



        ORDER BY queue_id



        LIMIT ?


        """



        return self.find_all(

            sql,

            (

                SyncStatus.WAITING,

                limit

            )

        )





    # =====================================================
    # Get Error Queue
    # =====================================================


    def get_error(
        self
    ):


        sql = """

        SELECT *

        FROM tb_sync_queue



        WHERE

        sync_status = ?



        ORDER BY queue_id


        """



        return self.find_all(

            sql,

            (

                SyncStatus.ERROR,

            )

        )





    # =====================================================
    # Mark Success
    # =====================================================


    def mark_success(
        self,
        transaction_guid
    ):


        sql = """

        UPDATE tb_sync_queue


        SET

            sync_status = ?,


            sync_date = datetime('now')



        WHERE

            transaction_guid = ?


        """



        return self.db.execute(

            sql,

            (

                SyncStatus.SUCCESS,

                transaction_guid

            )

        )





    # =====================================================
    # Mark Error
    # =====================================================


    def mark_error(
        self,
        transaction_guid,
        message
    ):


        sql = """

        UPDATE tb_sync_queue


        SET


            sync_status = ?,


            retry_count = retry_count + 1,


            error_message = ?



        WHERE

            transaction_guid = ?


        """



        return self.db.execute(

            sql,

            (

                SyncStatus.ERROR,

                message,

                transaction_guid

            )

        )





    # =====================================================
    # Reset Retry
    # =====================================================


    def reset_error(
        self,
        transaction_guid
    ):


        sql = """

        UPDATE tb_sync_queue


        SET


            sync_status = ?,


            error_message = ''



        WHERE

            transaction_guid = ?


        """



        return self.db.execute(

            sql,

            (

                SyncStatus.WAITING,

                transaction_guid

            )

        )