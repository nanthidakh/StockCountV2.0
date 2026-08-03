"""
=========================================================
Project : HWK_StockV1
File    : repository/plan_repository.py

Plan Repository

=========================================================
"""


from repository.base_repository import BaseRepository


from models.plan import Plan, PlanDetail





class PlanRepository(
    BaseRepository
):



    # =====================================================
    # Save Plan
    # =====================================================


    def save_plan(
        self,
        plan: Plan
    ):


        return self.insert(

            "tbt_plans",

            {


                "plan_id":

                plan.plan_id,


                "plan_name":

                plan.plan_name,


                "status":

                plan.status,


                "download_status":

                plan.download_status,


                "create_date":

                plan.create_date,


                "download_date":

                plan.download_date

            }

        )





    # =====================================================
    # Save Plan Detail
    # =====================================================


    def save_plan_detail(
        self,
        detail: PlanDetail
    ):


        return self.insert(

            "tbt_plan_details",

            {


                "plan_detail_id":

                detail.plan_detail_id,


                "plan_id":

                detail.plan_id,


                "item_id":

                detail.item_id,


                "location_id":

                detail.location_id,


                "before_location":

                detail.before_location,


                "qty":

                detail.qty,


                "qty_on_hand":

                detail.qty_on_hand,


                "qty_audit":

                detail.qty_audit,


                "is_check":

                detail.is_check

            }

        )





    # =====================================================
    # Find Plan Detail
    # =====================================================


    def find_plan_detail(
        self,
        plan_id,
        location_id,
        item_id
    ):


        sql = """

        SELECT *

        FROM tbt_plan_details


        WHERE

        plan_id = ?

        AND

        location_id = ?

        AND

        item_id = ?


        LIMIT 1

        """



        return self.find_one(

            sql,

            (

                plan_id,

                location_id,

                item_id

            )

        )





    # =====================================================
    # Get Plan Detail By ID
    # =====================================================


    def get_detail(
        self,
        plan_detail_id
    ):


        sql = """

        SELECT *

        FROM tbt_plan_details


        WHERE

        plan_detail_id = ?

        """



        return self.find_one(

            sql,

            (

                plan_detail_id,

            )

        )





    # =====================================================
    # Mark Download
    # =====================================================


    def mark_download(
        self,
        plan_id
    ):


        return self.update(

            "tbt_plans",

            {


                "download_status":

                1

            },

            "plan_id = ?",

            [

                plan_id

            ]

        )
    
    def get_current_plan(self):
    
        sql = """
        SELECT
            p.plan_id,
            p.plan_name,
            p.status,
            p.download_status,
            p.download_date,
            COUNT(pd.plan_detail_id) AS total_items
        FROM tb_plan AS p

        LEFT JOIN tb_plan_detail AS pd
            ON pd.plan_id = p.plan_id

        WHERE p.download_status = 1

        GROUP BY
            p.plan_id,
            p.plan_name,
            p.status,
            p.download_status,
            p.download_date

        ORDER BY
            p.download_date DESC,
            p.plan_id DESC

        LIMIT 1
        """

        return self.find_one(sql)