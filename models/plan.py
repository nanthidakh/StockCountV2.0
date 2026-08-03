"""
=========================================================
Project : HWK_StockV1
File    : models/plan.py

Plan Data Model

Python 3.11

=========================================================
"""


from dataclasses import dataclass, field

from datetime import datetime



# =====================================================
# Plan Header
# =====================================================


@dataclass
class Plan:


    plan_id: int


    plan_name: str = ""


    status: int = 0


    download_status: int = 0


    create_date: str = field(

        default_factory=lambda:

        datetime.now().isoformat()

    )


    download_date: str | None = None





    def is_downloaded(
        self
    ) -> bool:


        return (

            self.download_status == 1

        )





    def close(
        self
    ):


        self.status = 1





# =====================================================
# Plan Detail
# =====================================================


@dataclass
class PlanDetail:


    plan_detail_id: int


    plan_id: int


    item_id: int


    location_id: int



    before_location: str = ""



    qty: float = 0



    qty_on_hand: float = 0



    qty_audit: float = 0



    is_check: int = 0





    def add_qty(
        self,
        qty
    ):


        """

        กรณี Duplicate

        ADD


        """


        self.qty_on_hand += qty





    def replace_qty(
        self,
        qty
    ):


        """

        กรณี Duplicate

        REPLACE


        """


        self.qty_on_hand = qty





    def check(
        self
    ):


        self.is_check = 1