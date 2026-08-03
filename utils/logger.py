"""
=========================================================
Project : HWK_StockV1
File    : utils/logger.py

Application Logger

=========================================================
"""


import logging

import os





LOG_PATH = "logs"



if not os.path.exists(LOG_PATH):

    os.makedirs(LOG_PATH)





logger = logging.getLogger(

    "HWK_StockV1"

)



logger.setLevel(

    logging.DEBUG

)





formatter = logging.Formatter(

    "%(asctime)s | %(levelname)s | %(message)s"

)





file_handler = logging.FileHandler(

    os.path.join(

        LOG_PATH,

        "app.log"

    ),

    encoding="utf-8"

)



file_handler.setFormatter(

    formatter

)





logger.addHandler(

    file_handler

)





console_handler = logging.StreamHandler()



console_handler.setFormatter(

    formatter

)



logger.addHandler(

    console_handler

)