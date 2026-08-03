"""
=========================================================
Project : HWK_StockV1
File    : app.py
Main KivyMD Application
Python 3.11
Kivy 2.3.x
KivyMD 2.0.x
=========================================================
"""
from screens.main_menu_screen import MainMenuScreen
from screens.download_screen import DownloadScreen
from screens.count_screen import CountScreen
from screens.audit_screen import AuditScreen
from screens.correction_screen import CorrectionScreen
from screens.sync_screen import SyncScreen
from kivymd.app import MDApp
from kivy.lang import Builder
from utils.config import Config
from utils.logger import logger
from utils.device import get_device_name
from database.sqlite_db import SQLiteDB
from database.init_db import init_database
from screens.config_screen import ConfigScreen
from screens.launcher_screen import LauncherScreen
from countstock.database import init_db as init_countstock_db
from repository.config_repository import ConfigRepository

class HWKStockApp(MDApp):
    version = Config.VERSION
    db = None
    plan_id = None
    download_url = ""
    sync_url = ""
    login_url = ""
    sync_batch = 500
    timeout = 120
    def build(self):
    
        # ================================================
        # Config
        # ================================================
        Config.ensure_folder()

        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"

        # Force all KivyMD text styles (titles, hints, dialogs and list rows)
        # to use the registered Thai font. Icons must keep their icon font.
        try:
            for style_name, style_value in list(self.theme_cls.font_styles.items()):
                if style_name == "Icons":
                    continue
                updated = list(style_value)
                if updated:
                    updated[0] = "ThaiFont"
                    self.theme_cls.font_styles[style_name] = updated
        except Exception as exc:
            logger.warning(f"Unable to apply Thai font styles: {exc}")

        self.title = Config.APP_NAME

        # ================================================
        # Device
        # ================================================
        Config.DEVICE_NAME = get_device_name()
        self.device_name = str(Config.DEVICE_NAME or "").strip() or "UNKNOWN_DEVICE"

        logger.info(
            f"Device : {self.device_name}"
        )

        # ================================================
        # SQLite Database
        # ================================================
        self.db = SQLiteDB(
            Config.DB_PATH
        )

        self.db.connect()

        # Create and upgrade SQLite schema before reading app_config.
        # A fresh Android installation starts with an empty database file.
        init_database(
            self.db
        )

        logger.info(
            "Database Ready"
        )

        repo = ConfigRepository(
            self.db
        )
        config = repo.get_config()
        self.download_url = config.get(
            "download_url",
            ""
        )
        self.sync_url = config.get(
            "sync_url",
            ""
        )
        self.login_url = config.get(
            "login_url",
            ""
        )
        self.sync_batch = int(
            config.get(
                "sync_batch",
                500
            )
        )
        self.timeout = int(
            config.get(
                "timeout",
                120
            )
        )      
        

        # ================================================
        # Initialize CountStock Database
        # ================================================
        init_countstock_db()

        # ================================================
        # Load KV Files
        # ================================================
        Builder.load_file("kv/launcher.kv")
        Builder.load_file("kv/main_menu.kv")
        Builder.load_file("kv/countstock.kv")
        Builder.load_file("kv/config.kv")
        Builder.load_file("kv/download.kv")
        Builder.load_file("kv/count_screen.kv")
        Builder.load_file("kv/audit_screen.kv")
        Builder.load_file("kv/correction_screen.kv")
        Builder.load_file("kv/sync_screen.kv")

        logger.info(
            "KV Loaded"
        )

        print("KV LOADED")

        # ================================================
        # Main Screen Manager
        # ================================================
        root = Builder.load_file(
            "main.kv"
        )

        root.current = "launcher"

        print("=" * 50)
        print(root.screen_names)
        print("=" * 50)

        return root

    def on_stop(self):
        if self.db:
            self.db.close()
        logger.info(
            "Application Closed"
        )