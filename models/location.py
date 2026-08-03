"""
=========================================================
Project : HWK_StockV1
File    : models/location.py

Location Data Model

Python 3.11

=========================================================
"""


from dataclasses import dataclass, field

from datetime import datetime





# =====================================================
# Location Model
# =====================================================


@dataclass
class Location:


    location_id: int = 0


    location_name: str = ""


    zone_name: str = ""


    location_barcode: str = ""



    # 0 = Existing

    # 1 = Created from App


    is_new: int = 0



    create_date: str = field(

        default_factory=lambda:

        datetime.now().isoformat()

    )



    sync_status: int = 0





    # =================================================
    # New Location
    # =================================================


    @classmethod

    def create_new(
        cls,
        barcode,
        name=""
    ):


        """

        Create Location Offline


        Requirement:


        Scan Location

        ไม่พบใน Plan


        สามารถสร้าง Location ใหม่


        """


        return cls(


            location_id=0,


            location_name=name,


            location_barcode=barcode,


            is_new=1


        )





    # =================================================
    # Check New
    # =================================================


    def is_new_location(
        self
    ) -> bool:


        return self.is_new == 1





    # =================================================
    # Mark Sync
    # =================================================


    def mark_sync(
        self
    ):


        self.sync_status = 1





    # =================================================
    # Dictionary
    # =================================================


    def to_dict(
        self
    ):


        return {


            "location_id":

            self.location_id,


            "location_name":

            self.location_name,


            "zone_name":

            self.zone_name,


            "location_barcode":

            self.location_barcode,


            "is_new":

            self.is_new


        }