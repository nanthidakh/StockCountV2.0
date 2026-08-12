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
from kivymd.uix.textfield import MDTextField


class ScannerTextField(MDTextField):
    """TextField สำหรับ Hardware Scanner: consume Enter ไม่ให้ไหลไป focus navigation."""

    def keyboard_on_key_down(self, window, keycode, text, modifiers):
        key_num = keycode[0] if isinstance(keycode, (tuple, list)) and keycode else keycode
        key_name = (
            str(keycode[1]).lower()
            if isinstance(keycode, (tuple, list)) and len(keycode) > 1
            else ""
        )

        # Scanner มักปิดท้ายด้วย Enter / Numpad Enter
        # Dispatch on_text_validate เพียงครั้งเดียวแล้ว consume event ทันที
        if key_num in (13, 271) or key_name in ("enter", "numpadenter", "kp_enter"):
            if not self.disabled:
                self.dispatch("on_text_validate")
            return True

        return super().keyboard_on_key_down(window, keycode, text, modifiers)


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
    
