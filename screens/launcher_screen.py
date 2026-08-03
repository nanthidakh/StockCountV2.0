from kivy.app import App
from kivymd.uix.screen import MDScreen


class LauncherScreen(MDScreen):
    def open_countstock(self):
        self.manager.current = "countstock_menu"

    def open_hwk_stock(self):
        self.manager.current = "main_menu"

    def exit_app(self):
        App.get_running_app().stop()
