"""
=========================================================
Project : HWK_StockV1
File    : screens/login_screen.py
Login Screen
KivyMD 2.0.x
=========================================================
"""
from kivy.clock import Clock
from kivymd.uix.screen import MDScreen
from models.user import User
from kivy.app import App
class LoginScreen(MDScreen):
    user = None
    from kivy.app import App
    def login(
            self
        ):
        username = (
            self.ids.txt_username.text.strip()
        )
        device = (
            self.ids.txt_device.text.strip()
        )
        if not username:
            self.show_message(
                "กรุณาระบุ User"
            )
            return
        if not device:
            self.show_message(
                "กรุณาระบุ Device"
            )
            return
        self.user = User(
            user_code=username,
            user_name=username
        )
        self.user.login(
            device
        )
        # เก็บ Session ใน App หลัก
        app = App.get_running_app()
        app.user = self.user
        Clock.schedule_once(
            lambda x:
            self.go_main(),
            0.2
        )
        def go_main(
            self
        ):
            self.manager.current = (
                "main_menu"
            )
    def show_message(
        self,
        text
    ):
        self.ids.lbl_message.text = text