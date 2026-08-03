"""
=========================================================
Project : HWK_StockV1
File    : widgets/product_card.py

Product Display Card

=========================================================
"""


from kivymd.uix.card import MDCard

from kivy.properties import (

    StringProperty

)





class ProductCard(
    MDCard
):


    item_code = StringProperty(
        ""
    )


    item_name = StringProperty(
        ""
    )


    qty = StringProperty(
        "0"
    )


    location = StringProperty(
        ""
    )


    barcode = StringProperty(
        ""
    )