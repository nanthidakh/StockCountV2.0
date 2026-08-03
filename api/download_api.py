"""
=========================================================
Project : HWK_StockV1
File    : api/download_api.py
Download API
=========================================================
"""
from api.api_client import APIClient
class DownloadAPI:
    def __init__(
        self,
        client: APIClient
    ):
        self.client = client
    # =====================================================
    # Get Plan
    # =====================================================
    def get_plan(
        self,
        plan_id
    ):
        return self.client.post(
            "/stock/download_plan",
            {
                "plan_id":
                plan_id
            }
        )