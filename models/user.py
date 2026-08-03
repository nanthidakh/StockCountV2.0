"""
=========================================================
Project : HWK_StockV1
File    : models/user.py

User Data Model

Python 3.11

=========================================================
"""


from dataclasses import dataclass, field

from datetime import datetime





# =====================================================
# User Role
# =====================================================


class UserRole:


    COUNT = "COUNT"


    AUDIT = "AUDIT"


    ADMIN = "ADMIN"





# =====================================================
# User Model
# =====================================================


@dataclass
class User:



    user_id: int = 0



    user_code: str = ""



    user_name: str = ""



    device_name: str = ""



    role: str = (

        UserRole.COUNT

    )



    login_status: int = 0



    login_date: str | None = None



    logout_date: str | None = None



    create_date: str = field(

        default_factory=lambda:

        datetime.now().isoformat()

    )





    # =================================================
    # Login
    # =================================================


    def login(
        self,
        device_name
    ):


        self.device_name = device_name


        self.login_status = 1


        self.login_date = (

            datetime.now().isoformat()

        )





    # =================================================
    # Logout
    # =================================================


    def logout(
        self
    ):


        self.login_status = 0


        self.logout_date = (

            datetime.now().isoformat()

        )





    # =================================================
    # Check Permission
    # =================================================


    def can_audit(
        self
    ):


        return self.role in [

            UserRole.AUDIT,

            UserRole.ADMIN

        ]





    # =================================================
    # Dictionary
    # =================================================


    def to_dict(
        self
    ):


        return {


            "user_id":

            self.user_id,


            "user_code":

            self.user_code,


            "user_name":

            self.user_name,


            "device_name":

            self.device_name,


            "role":

            self.role,


            "login_status":

            self.login_status


        }