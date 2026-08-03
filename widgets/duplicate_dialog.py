"""
=========================================================
Project : HWK_StockV1
File    : widgets/duplicate_dialog.py

Duplicate Count Dialog

=========================================================
"""


from kivymd.uix.dialog import MDDialog

from kivymd.uix.button import MDFlatButton





class DuplicateDialog:



    def __init__(
        self,
        callback
    ):


        self.callback = callback


        self.dialog = MDDialog(

            title="พบรายการซ้ำ",


            text=(

                "สินค้านี้ถูกนับแล้ว\n"

                "ต้องการดำเนินการอย่างไร?"

            ),


            buttons=[


                MDFlatButton(

                    text="ADD",

                    on_release=lambda x:

                    self.select(

                        "ADD"

                    )

                ),



                MDFlatButton(

                    text="REPLACE",

                    on_release=lambda x:

                    self.select(

                        "REPLACE"

                    )

                ),



                MDFlatButton(

                    text="CANCEL",

                    on_release=lambda x:

                    self.select(

                        "CANCEL"

                    )

                )


            ]

        )





    def open(
        self
    ):


        self.dialog.open()





    def select(
        self,
        action
    ):


        self.dialog.dismiss()



        if self.callback:


            self.callback(

                action

            )