"""
=========================================================
Project : HWK_StockV1
File    : models/item.py

Item Data Model

Python 3.11

=========================================================
"""


from dataclasses import dataclass, field



# =====================================================
# Item Master
# =====================================================


@dataclass
class Item:


    item_id: int


    item_code: str = ""


    item_name: str = ""


    unit_name: str = ""



    # List Barcode ของสินค้า

    barcodes: list[str] = field(

        default_factory=list

    )





    # =================================================
    # Add Barcode
    # =================================================


    def add_barcode(
        self,
        barcode: str
    ):


        """

        1 Item

        Many Barcode


        """


        if barcode not in self.barcodes:


            self.barcodes.append(

                barcode

            )





    # =================================================
    # Check Barcode
    # =================================================


    def has_barcode(
        self,
        barcode: str
    ) -> bool:


        return barcode in self.barcodes





    # =================================================
    # Convert Dictionary
    # =================================================


    def to_dict(
        self
    ):


        return {


            "item_id":

            self.item_id,


            "item_code":

            self.item_code,


            "item_name":

            self.item_name,


            "unit_name":

            self.unit_name,


            "barcodes":

            self.barcodes


        }