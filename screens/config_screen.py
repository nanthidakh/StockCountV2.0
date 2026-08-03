"""
=========================================================
Project : HWK_StockV1
File : screens/config_screen.py
=========================================================
"""
from kivy.app import App
from screens.base_screen import BaseScreen
from repository.config_repository import ConfigRepository
from services.config_service import ConfigService
from utils.device import get_device_name
class ConfigScreen(BaseScreen):
    # =====================================================
    # Screen Open
    # =====================================================
    def on_enter(self):
        app = App.get_running_app()
        self.ids.lbl_device_name.text = get_device_name()
        repo = ConfigRepository(app.db)
        config = repo.get_config()
        self.ids.txt_server_ip.text = config.get(
            "server_ip",
            ""
        )
        if config.get("download_url", "") != "":
            self.ids.lbl_status.text = "Connected"
        else:
            self.ids.lbl_status.text = "Not Connected"
    # =====================================================
    # Connect Server
    # =====================================================
    def connect_server(self):
        server_ip = self.ids.txt_server_ip.text.strip()
        if server_ip == "":
            self.show_error(
                "กรุณาระบุ Server IP"
            )
            return
        self.show_loading(
            "Connecting..."
        )
        self.delay(
            lambda:
            self.load_config(server_ip)
        )
    # =====================================================
    # Download Config
    # =====================================================
    def load_config(
        self,
        server_ip
    ):
        app = App.get_running_app()
        try:
            service = ConfigService()
            config = service.download_config(
                server_ip
            )
            repo = ConfigRepository(
                app.db
            )
            # -----------------------------
            # Save Server IP
            # -----------------------------
            repo.save(
                "server_ip",
                server_ip
            )
            # -----------------------------
            # Save All Config
            # -----------------------------
            repo.save_config(
                config
            )
            # -----------------------------
            # Runtime
            # -----------------------------
            app.download_url = config[
                "download_url"
            ]
            app.sync_url = config[
                "sync_url"
            ]
            app.login_url = config[
                "login_url"
            ]
            app.sync_batch = int(
                config["sync_batch"]
            )
            app.timeout = int(
                config["timeout"]
            )
            self.hide_loading()
            self.ids.lbl_status.text = (
                "Connected"
            )
            self.show_success(
                "Connected Successfully"
            )
        except Exception as e:
            self.hide_loading()
            self.show_error(
                str(e)
            )