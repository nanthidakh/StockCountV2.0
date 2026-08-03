"""
=========================================================
Project : HWK_StockV1
File    : api/sync_api.py

Sync API

=========================================================
"""


from api.api_client import APIClient





class SyncAPI:



    def __init__(
        self,
        client: APIClient
    ):


        self.client = client





    # =====================================================
    # Batch Sync
    # =====================================================


    def send_batch(
        self,
        transactions
    ):


        payload = {


            "transactions":

            transactions


        }



        return self.client.post(

            "/stock/sync",

            payload

        )