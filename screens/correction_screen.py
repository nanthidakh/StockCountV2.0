"""
=========================================================
Project : HWK_StockV1
File    : screens/correction_screen.py

Correction Screen
=========================================================
"""

from kivy.app import App
from kivy.clock import Clock

from screens.base_screen import BaseScreen
from services.correction_service import CorrectionService


class CorrectionScreen(BaseScreen):
    selected_transaction = None
    selected_transactions = None
    correction_mode = "QTY"

    def on_pre_enter(self, *args):
        """CorrectionScreen รับ Mode จาก Tab ล่าสุดเท่านั้น"""
        app = App.get_running_app()
        mode = str(getattr(app, "correction_mode", "QTY") or "QTY").upper()

        if mode == "LOCATION":
            rows = getattr(app, "selected_count_transactions", None) or []
            self.open_for_location(rows)
        else:
            row = getattr(app, "selected_count_transaction", None)
            if row:
                self.open_for_qty(row)
            else:
                self.clear_selection(mode="QTY")

    def open_for_qty(self, transaction):
        """เปิดหน้า Correction ใน Mode แก้จำนวนเพียงรายการเดียว"""
        app = App.get_running_app()
        app.correction_mode = "QTY"
        app.selected_count_transactions = None
        self.set_selected_transaction(transaction)

    def open_for_location(self, transactions):
        """เปิดหน้า Correction ใน Mode แก้ Location หลายรายการ"""
        app = App.get_running_app()
        app.correction_mode = "LOCATION"
        app.selected_count_transaction = None
        self.set_selected_transactions_location(transactions)

    def set_selected_transaction(self, transaction):
        """แก้จำนวนได้ครั้งละ 1 รายการเท่านั้น"""
        self.correction_mode = "QTY"
        self.selected_transaction = dict(transaction)
        self.selected_transactions = None

        item_code = self._value(transaction, "item_code", "-")
        location_code = self._value(transaction, "location_code", "-")
        qty = self._value(transaction, "qty", "")
        uom = self._value(transaction, "uom", "-") or "-"

        self.ids.lbl_title.text = "แก้ไขจำนวน"
        self.ids.lbl_mode.text = "MODE: แก้จำนวน (1 รายการ)"
        self.ids.mode_card.md_bg_color = (0.88, 1.0, 0.90, 1)
        self.ids.lbl_selected.text = (
            f"LOC: {location_code}\n"
            f"รหัสสินค้า: {item_code}\n"
            f"จำนวนเดิม: {self._format_qty(qty)} {uom}"
        )
        self.ids.txt_qty.text = ""
        self.ids.txt_qty.disabled = False
        self.ids.txt_qty.opacity = 1
        self.ids.txt_qty.height = "68dp"

        self.ids.txt_location.text = ""
        self.ids.txt_location.disabled = True
        self.ids.txt_location.opacity = 0
        self.ids.txt_location.height = "0dp"

        self.ids.btn_save.text = "บันทึกจำนวน"
        self.ids.lbl_status.text = "กรอกจำนวนใหม่ แล้วกดบันทึก"
        Clock.schedule_once(lambda dt: self._focus_qty(), 0.1)

    def set_selected_transactions_location(self, transactions):
        """แก้ Location หลายรายการพร้อมกัน"""
        rows = [dict(row) for row in (transactions or [])]
        self.correction_mode = "LOCATION"
        self.selected_transaction = None
        self.selected_transactions = rows

        self.ids.lbl_title.text = "แก้ไข Location"
        self.ids.lbl_mode.text = "MODE: แก้ LOCATION (หลายรายการ)"
        self.ids.mode_card.md_bg_color = (1.0, 0.93, 0.82, 1)
        self.ids.lbl_selected.text = (
            f"เลือกรายการแล้ว: {len(rows)} รายการ\n"
            "ยิงหรือกรอก Location ใหม่ด้านล่าง"
        )

        self.ids.txt_qty.text = ""
        self.ids.txt_qty.disabled = True
        self.ids.txt_qty.opacity = 0
        self.ids.txt_qty.height = "0dp"

        self.ids.txt_location.text = ""
        self.ids.txt_location.disabled = False
        self.ids.txt_location.opacity = 1
        self.ids.txt_location.height = "68dp"

        self.ids.btn_save.text = "บันทึก Location"
        self.ids.lbl_status.text = "Location ใหม่ต้องอยู่ใน Plan เดียวกัน"
        Clock.schedule_once(lambda dt: self._focus_location(), 0.1)

    def clear_selection(self, mode="QTY"):
        self.selected_transaction = None
        self.selected_transactions = None
        self.correction_mode = str(mode or "QTY").upper()

        if "lbl_mode" in self.ids:
            self.ids.lbl_mode.text = (
                "MODE: แก้ LOCATION"
                if self.correction_mode == "LOCATION"
                else "MODE: แก้จำนวน"
            )
        if "lbl_selected" in self.ids:
            self.ids.lbl_selected.text = "กรุณากลับไปเลือกรายการจาก Tab ล่าสุด"
        if "txt_qty" in self.ids:
            self.ids.txt_qty.text = ""
        if "txt_location" in self.ids:
            self.ids.txt_location.text = ""
        if "lbl_status" in self.ids:
            self.ids.lbl_status.text = "ไม่มีรายการที่เลือก"

    def save_correction(self):
        if self.correction_mode == "LOCATION":
            self.edit_location()
        else:
            self.edit_qty()

    def edit_qty(self):
        if not self.selected_transaction:
            self.ids.lbl_status.text = "กรุณาเลือกรายการจาก Tab ล่าสุด"
            self._play_error()
            return

        qty_text = str(self.ids.txt_qty.text or "").strip()
        if not qty_text:
            self.ids.lbl_status.text = "กรุณากรอกจำนวนใหม่"
            self._play_error()
            self._focus_qty()
            return

        try:
            new_qty = float(qty_text)
        except (TypeError, ValueError):
            self.ids.lbl_status.text = "จำนวนไม่ถูกต้อง"
            self._play_error()
            self._focus_qty()
            return

        app = App.get_running_app()
        checker = getattr(app, "device_name", "") or "ANDROID"
        service = CorrectionService(app.db)

        try:
            correction = service.correct_qty(
                self.selected_transaction,
                new_qty,
                checker,
            )
        except Exception as exc:
            self.ids.lbl_status.text = f"แก้ไขไม่สำเร็จ: {exc}"
            self._play_error()
            return

        self.ids.lbl_status.text = f"แก้ไขเป็น {new_qty:g} แล้ว รอ Sync"
        self.ids.txt_qty.text = ""
        app.selected_count_transaction = None
        self.selected_transaction = correction

    def edit_location(self):
        if not self.selected_transactions:
            self.ids.lbl_status.text = "กรุณาเลือกรายการจาก Tab ล่าสุด"
            self._play_error()
            return

        location_code = str(self.ids.txt_location.text or "").strip()
        if not location_code:
            self.ids.lbl_status.text = "กรุณายิงหรือกรอก Location ใหม่"
            self._play_error()
            self._focus_location()
            return

        app = App.get_running_app()
        checker = getattr(app, "device_name", "") or "ANDROID"
        service = CorrectionService(app.db)

        try:
            result = service.correct_locations(
                self.selected_transactions,
                location_code,
                checker,
            )
        except Exception as exc:
            self.ids.lbl_status.text = f"แก้ไข Location ไม่สำเร็จ: {exc}"
            self._play_error()
            return

        total = int(result.get("updated", 0))
        resolved_code = str(result.get("location_code") or location_code).strip()
        resolved_id = result.get("location_id")
        self.ids.lbl_status.text = (
            f"เปลี่ยน Location เป็น {resolved_code} "
            f"(Server ID: {resolved_id}) แล้ว {total} รายการ รอ Sync"
        )
        self.ids.txt_location.text = ""
        app.selected_count_transactions = None
        self.selected_transactions = None

    def go_count_recent(self):
        if not self.manager or not self.manager.has_screen("count"):
            return

        app = App.get_running_app()
        mode = str(self.correction_mode or "QTY").upper()
        app.correction_mode = mode
        app.selected_count_transaction = None
        app.selected_count_transactions = None

        count_screen = self.manager.get_screen("count")
        count_screen._return_tab = "recent_tab"
        count_screen.correction_selection_mode = mode
        count_screen.location_selection_mode = mode == "LOCATION"
        count_screen.selected_recent_rows = {}
        count_screen._update_correction_mode_ui()

        self.manager.current = "count"
        Clock.schedule_once(lambda dt: count_screen.switch_tab("recent_tab"), 0.1)

    def _focus_qty(self):
        if "txt_qty" in self.ids and not self.ids.txt_qty.disabled:
            self.ids.txt_qty.focus = True

    def _focus_location(self):
        if "txt_location" in self.ids and not self.ids.txt_location.disabled:
            self.ids.txt_location.focus = True

    def _play_error(self):
        if self.manager and self.manager.has_screen("count"):
            self.manager.get_screen("count").play_error_sound()

    @staticmethod
    def _value(source, key, default=None):
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    @staticmethod
    def _format_qty(value):
        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            return str(value)
