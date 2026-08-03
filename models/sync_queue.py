"""
=========================================================
Project : HWK_StockV1
File    : models/sync_queue.py

Offline Sync Queue Model

Python 3.11

=========================================================
"""


from dataclasses import dataclass, field

from datetime import datetime



# =====================================================
# Sync Status
# =====================================================


class SyncStatus:


    WAITING = 0


    SUCCESS = 1


    ERROR = 2





# =====================================================
# Sync Queue Model
# =====================================================


@dataclass
class SyncQueue:



    queue_id: int = 0



    transaction_guid: str = ""



    transaction_type: str = ""



    payload_json: str = ""



    sync_status: int = (

        SyncStatus.WAITING

    )



    retry_count: int = 0



    error_message: str = ""



    create_date: str = field(

        default_factory=lambda:

        datetime.now().isoformat()

    )



    sync_date: str | None = None





    # =================================================
    # Mark Success
    # =================================================


    def mark_success(
        self
    ):


        self.sync_status = (

            SyncStatus.SUCCESS

        )


        self.sync_date = (

            datetime.now().isoformat()

        )





    # =================================================
    # Mark Error
    # =================================================


    def mark_error(
        self,
        message
    ):


        self.sync_status = (

            SyncStatus.ERROR

        )


        self.error_message = message



        self.retry_count += 1





    # =================================================
    # Retry
    # =================================================


    def can_retry(
        self,
        max_retry=5
    ):


        return (

            self.retry_count < max_retry

        )





    # =================================================
    # Dictionary
    # =================================================


    def to_dict(
        self
    ):


        return {


            "queue_id":

            self.queue_id,


            "transaction_guid":

            self.transaction_guid,


            "transaction_type":

            self.transaction_type,


            "payload_json":

            self.payload_json,


            "sync_status":

            self.sync_status,


            "retry_count":

            self.retry_count,


            "error_message":

            self.error_message,


            "create_date":

            self.create_date,


            "sync_date":

            self.sync_date


        }