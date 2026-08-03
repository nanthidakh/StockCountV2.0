"""
=========================================================
Project : HWK_StockV1
File    : screens/base_screen.py
Base Screen
=========================================================
"""
from kivy.clock import Clock
from kivymd.uix.screen import MDScreen
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
class BaseScreen(MDScreen):
    dialog = None
    # =====================================================
    # Navigation
    # =====================================================
    def go_main(self):
        self.manager.current = "main_menu"
    def go_download(self):
        self.manager.current = "download"
    def go_count(self):
        self.manager.current = "count"
    def go_audit(self):
        self.manager.current = "audit"
    def go_correction(self):
        self.manager.current = "correction"
    def go_sync(self):
        self.manager.current = "sync"
    def go_Exit(self):
            self.manager.current = "exit"
    # =====================================================
    # Dialog
    # =====================================================
    def show_message(self, title, text):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(
            title=title,
            text=text,
            buttons=[
                MDFlatButton(
                    text="OK",
                    on_release=lambda x: self.close_dialog()
                )
            ]
        )
        self.dialog.open()
    def show_error(self, text):
        self.show_message("Error", text)
    def show_success(self, text):
        self.show_message("Success", text)
    def close_dialog(self, *args):
        if self.dialog:
            self.dialog.dismiss()
            self.dialog = None
    # =====================================================
    # Loading
    # =====================================================
    def show_loading(self, text="Loading..."):
        self.close_dialog()
        self.dialog = MDDialog(
            title="Please Wait",
            text=text
        )
        self.dialog.open()
    def hide_loading(self):
        self.close_dialog()
    # =====================================================
    # Status Label
    # =====================================================
    def set_status(self, text):
        if "lbl_status" in self.ids:
            self.ids.lbl_status.text = text
    # =====================================================
    # Progress Bar
    # =====================================================
    def set_progress(self, value):
        if "progress" in self.ids:
            self.ids.progress.value = value
    # =====================================================
    # Label
    # =====================================================
    def set_label(self, widget_id, value):
        if widget_id in self.ids:
            self.ids[widget_id].text = str(value)
    # =====================================================
    # Focus
    # =====================================================
    def focus(self, widget_id):
        if widget_id in self.ids:
            self.ids[widget_id].focus = True
    # =====================================================
    # Clear Text
    # =====================================================
    def clear_text(self, widget_id):
        if widget_id in self.ids:
            self.ids[widget_id].text = ""
    # =====================================================
    # Enable Widget
    # =====================================================
    def enable(self, widget_id):
        if widget_id in self.ids:
            self.ids[widget_id].disabled = False
    # =====================================================
    # Disable Widget
    # =====================================================
    def disable(self, widget_id):
        if widget_id in self.ids:
            self.ids[widget_id].disabled = True
    # =====================================================
    # Delay
    # =====================================================
    def delay(self, callback, second=.1):
        Clock.schedule_once(
            lambda dt: callback(),
            second
        )
    # =====================================================
    # Reset Screen
    # =====================================================
    def reset(self):
        pass
    
