"""
=========================================================
Project : HWK_StockV1
File    : widgets/scan_widget.py

Barcode Scanner Widget

=========================================================
"""


from kivy.uix.boxlayout import BoxLayout

from kivy.properties import StringProperty





class ScanWidget(
    BoxLayout
):


    barcode = StringProperty(
        ""
    )





    def receive_barcode(
        self,
        code
    ):


        self.barcode = code



        if self.parent:


            if hasattr(

                self.parent,

                "on_barcode"

            ):


                self.parent.on_barcode(

                    code

                )