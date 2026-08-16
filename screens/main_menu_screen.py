"""
=========================================================
Project : HWK_StockV1
File    : screens/main_menu_screen.py
Purpose : Main menu + Developer reset local database
=========================================================
"""

from __future__ import annotations

from kivy.app import App
from kivy.clock import Clock
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen

from services.developer_service import DeveloperService


class MainMenuScreen(MDScreen):
    _dialog = None
    _reset_running = False

    def on_enter(self, *args):
        app = App.get_running_app()
        if "lbl_device" in self.ids:
            self.ids.lbl_device.text = (
                "ชื่อเครื่อง: "
                + str(getattr(app, "device_name", "") or "UNKNOWN_DEVICE")
            )
        if "lbl_status" in self.ids:
            self.ids.lbl_status.text = "เลือกเมนูที่ต้องการใช้งาน"


    def go_launcher(self):
        """Return to the combined-program launcher."""
        if self.manager and self.manager.has_screen("launcher"):
            self.manager.current = "launcher"

    def go_to(self, *screen_names):
        if not self.manager:
            return

        for screen_name in screen_names:
            if screen_name and self.manager.has_screen(screen_name):
                self.manager.current = screen_name
                return

        self._show_message(
            "ไม่พบหน้าจอ",
            "ไม่พบชื่อหน้าจอ: " + ", ".join(screen_names),
        )


    def confirm_exit_app(self):
        """Confirm before closing the Android/Windows application."""
        self._dismiss_dialog()
        self._dialog = MDDialog(
            title="ออกจากโปรแกรม",
            text="ต้องการออกจากโปรแกรมหรือไม่?",
            buttons=[
                MDFlatButton(
                    text="ยกเลิก",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._dismiss_dialog(),
                ),
                MDRaisedButton(
                    text="ออก",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._exit_app(),
                ),
            ],
        )
        self._dialog.open()

    def _exit_app(self):
        self._dismiss_dialog()
        App.get_running_app().stop()

    def confirm_reset_local_database(self):
        if self._reset_running:
            return

        self._dismiss_dialog()

        self._dialog = MDDialog(
            title="ยืนยันล้างข้อมูลในเครื่อง",
            text=(
                "ข้อมูล Plan, Count, Correction, Audit และ Sync Queue "
                "ใน SQLite ของเครื่องนี้จะถูกลบทั้งหมด\n\n"
                "Device ID และการตั้งค่า API จะยังคงอยู่\n\n"
                "ต้องการดำเนินการต่อหรือไม่?"
            ),
            buttons=[
                MDFlatButton(
                    text="ยกเลิก",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._dismiss_dialog(),
                ),
                MDRaisedButton(
                    text="ล้างข้อมูล",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._start_reset(),
                ),
            ],
        )
        self._dialog.open()

    def _start_reset(self):
        self._dismiss_dialog()

        if self._reset_running:
            return

        self._reset_running = True
        if "lbl_status" in self.ids:
            self.ids.lbl_status.text = "กำลังล้างข้อมูลในเครื่อง..."
        if "btn_reset_local" in self.ids:
            self.ids.btn_reset_local.disabled = True

        Clock.schedule_once(self._execute_reset, 0.05)

    def _execute_reset(self, _dt):
        app = App.get_running_app()

        try:
            result = DeveloperService(app.db).reset_local_database()
            deleted_total = sum(int(value or 0) for value in result.values())

            # Clear app runtime context
            app.plan_id = None
            if hasattr(app, "current_plan"):
                app.current_plan = None
            if hasattr(app, "correction_mode"):
                app.correction_mode = "QTY"
            if hasattr(app, "selected_correction_rows"):
                app.selected_correction_rows = []

            if "lbl_status" in self.ids:
                self.ids.lbl_status.text = "ล้างข้อมูลในเครื่องสำเร็จ"

            self._show_message(
                "สำเร็จ",
                (
                    "ล้างข้อมูลใน SQLite เรียบร้อยแล้ว\n"
                    f"ลบข้อมูลรวม {deleted_total:,} แถว\n\n"
                    "ขั้นตอนถัดไป: Download Plan ใหม่"
                ),
            )

        except Exception as error:
            if "lbl_status" in self.ids:
                self.ids.lbl_status.text = "ล้างข้อมูลไม่สำเร็จ"
            self._show_message(
                "เกิดข้อผิดพลาด",
                str(error),
            )
        finally:
            self._reset_running = False
            if "btn_reset_local" in self.ids:
                self.ids.btn_reset_local.disabled = False

    def _show_message(self, title, text):
        self._dismiss_dialog()
        self._dialog = MDDialog(
            title=str(title),
            text=str(text),
            buttons=[
                MDRaisedButton(
                    text="ตกลง",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._dismiss_dialog(),
                )
            ],
        )
        self._dialog.open()

    def _dismiss_dialog(self):
        dialog = self._dialog
        self._dialog = None
        if dialog:
            try:
                dialog.dismiss()
            except Exception:
                pass
