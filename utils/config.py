"""
=========================================================
Project : HWK_StockV1
File    : utils/config.py

Application Config

=========================================================
"""


import os





class Config:



    APP_NAME = (

        "HWK_StockV1"

    )



    VERSION = (

        "1.0.0"

    )





    # API


    API_URL = (

        "http://server/countstock"

    )





    # SQLite


    DB_PATH = (

        "data/hwk_stock.db"

    )





    # Sync


    SYNC_BATCH_SIZE = 500



    SYNC_TIMEOUT = 120





    # Device


    DEVICE_NAME = ""



    USER_CODE = ""





    @staticmethod

    def ensure_folder():



        folders = [


            "data",

            "logs"

        ]



        for folder in folders:



            if not os.path.exists(folder):


                os.makedirs(folder)