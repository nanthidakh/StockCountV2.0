"""
=========================================================
Project : HWK_StockV1
File    : api/api_client.py

Base API Client

=========================================================
"""


import requests



from utils.logger import logger





class APIClient:



    def __init__(
        self,
        base_url,
        timeout=60
    ):


        self.base_url = base_url.rstrip("/")


        self.timeout = timeout



        self.session = requests.Session()





    # =====================================================
    # POST
    # =====================================================


    def post(
        self,
        endpoint,
        data=None
    ):


        url = (

            self.base_url

            +

            "/"

            +

            endpoint.lstrip("/")

        )



        try:



            response = self.session.post(

                url,

                json=data,

                timeout=self.timeout

            )



            response.raise_for_status()



            return response.json()





        except Exception as e:



            logger.error(

                f"API POST ERROR {url}: {e}"

            )


            raise e





    # =====================================================
    # GET
    # =====================================================


    def get(
        self,
        endpoint,
        params=None
    ):


        url = (

            self.base_url

            +

            "/"

            +

            endpoint.lstrip("/")

        )



        try:



            response = self.session.get(

                url,

                params=params,

                timeout=self.timeout

            )



            response.raise_for_status()



            return response.json()




        except Exception as e:



            logger.error(

                f"API GET ERROR {url}: {e}"

            )


            raise e