"""
=========================================================
Project : HWK_StockV1
File    : screens/sync_screen.py
Sync Screen
=========================================================
"""
from kivymd.uix.screen import MDScreen
from services.sync_service import SyncService
from kivy.app import App
class SyncScreen(MDScreen):
    # =====================================================
    # Start Sync
    # =====================================================
    def start_sync(
        self
        ):
        try:
            app = App.get_running_app()
            service = SyncService(
                app.db
            )
            result = service.sync(
                app.api_url
            )
            self.ids.lbl_status.text = (
                "Sync Complete"
            )
            self.ids.lbl_success.text = (
                f"Success : {result.get('success',0)}"
            )
            self.ids.lbl_error.text = (
                f"Error : {result.get('error',0)}"
            )
        except Exception as e:
            self.ids.lbl_status.text = str(e)
    # =====================================================
    # Retry Error
    # =====================================================
    def retry_sync(
        self
        ):

        try:

            app = App.get_running_app()


            service = SyncService(

                app.db

            )


            result = service.retry_error(

                app.api_url

            )


            self.ids.lbl_status.text = (

                "Retry Complete"

            )


        except Exception as e:


            self.ids.lbl_status.text = str(e)