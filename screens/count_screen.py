"""
=========================================================
Project : HWK_StockV1
File    : screens/count_screen.py

Stock Count Screen
=========================================================
"""

import subprocess
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.utils import platform
from kivymd.uix.screen import MDScreen

from services.count_service import CountService
from services.sync_service import SyncService
from utils.config import Config


class CountScreen(MDScreen):

    # =====================================================
    # Current Screen State
    # =====================================================
    current_plan = None
    current_location = None
    current_location_data = None
    current_item = None
    _is_processing = False
    _sync_status_in_flight = False

    # =====================================================
    # Screen Enter
    # =====================================================
    def on_enter(self, *args):

        self.current_plan = None
        self.current_location = None
        self.current_item = None
        self._is_processing = False
        app = App.get_running_app()
        self.correction_selection_mode = str(
            getattr(app, "correction_mode", "QTY") or "QTY"
        ).upper()
        if self.correction_selection_mode not in ("QTY", "LOCATION"):
            self.correction_selection_mode = "QTY"
        self.location_selection_mode = self.correction_selection_mode == "LOCATION"
        self.selected_recent_rows = {}

        self._clear_item_display()

        self.ids.lbl_location.text = (
            "กรุณายิง Barcode Location"
        )

        self.ids.lbl_status.text = (
            "กำลังตรวจสอบข้อมูล Plan..."
        )

        self.ids.txt_qty.text = ""
        self.ids.txt_barcode.text = ""

        self._load_device_name()

        target_tab = getattr(self, "_return_tab", "count_tab")
        self._return_tab = "count_tab"

        if "count_tab_manager" in self.ids:
            self.ids.count_tab_manager.current = target_tab

        self._set_active_tab(target_tab)
        self.load_current_plan()

        if target_tab == "recent_tab":
            Clock.schedule_once(lambda dt: self.switch_tab("recent_tab"), 0.1)

    # =====================================================
    # Load Device Name
    # =====================================================
    def _load_device_name(self):

        app = App.get_running_app()

        device_name = str(
            getattr(app, "device_name", "")
            or getattr(Config, "DEVICE_NAME", "")
            or ""
        ).strip()

        if not device_name:
            device_name = "UNKNOWN_DEVICE"

        # ทำให้ทุก Tab และทุก Service ใช้ชื่อเครื่องจากแหล่งเดียวกัน
        app.device_name = device_name
        Config.DEVICE_NAME = device_name
        self.ids.txt_checker.text = device_name

    # =====================================================
    # Load Current Plan
    # =====================================================
    def load_current_plan(self):

        app = App.get_running_app()
        service = CountService(app.db)

        try:

            result = service.get_current_plan()

        except AttributeError:

            # รองรับกรณี CountService ยังไม่มี
            # get_current_plan()
            result = self._get_current_plan_fallback()

        except Exception as error:

            self.current_plan = None

            self.ids.lbl_plan_name.text = (
                "ไม่สามารถอ่านข้อมูล Plan ได้"
            )

            self.ids.lbl_plan_detail.text = ""

            self.ids.lbl_status.text = (
                f"เกิดข้อผิดพลาด: {error}"
            )
            self.play_error_sound()

            self.set_count_enabled(False)
            return

        status = result.get("status")

        # -------------------------------------------------
        # No Plan
        # -------------------------------------------------
        if status == "NO_PLAN":

            self.current_plan = None

            self.ids.lbl_plan_name.text = (
                "ยังไม่มีแผนตรวจนับ"
            )

            self.ids.lbl_plan_detail.text = (
                "กรุณา Download Plan ก่อนเริ่มนับ"
            )

            self.ids.lbl_status.text = (
                result.get(
                    "message",
                    "ไม่พบข้อมูล Plan"
                )
            )

            self.set_count_enabled(False)
            return

        plan = result.get("plan")

        if not plan:

            self.current_plan = None

            self.ids.lbl_plan_name.text = (
                "ไม่พบข้อมูล Plan"
            )

            self.ids.lbl_plan_detail.text = ""

            self.ids.lbl_status.text = (
                "กรุณา Download Plan ใหม่"
            )

            self.set_count_enabled(False)
            return

        self.current_plan = plan

        plan_id = self._row_value(plan, "plan_id")
        plan_code = self._row_value(plan, "plan_code", "")
        plan_name = self._row_value(plan, "plan_name", "")

        total_items = self._row_value(
            plan,
            "total_items",
            0
        )

        try:
            total_items = int(
                total_items or 0
            )
        except (TypeError, ValueError):
            total_items = 0

        if not plan_name:
            plan_name = f"Plan {plan_id}"

        # เก็บไว้ใน App สำหรับหน้าจออื่น
        app.plan_id = plan_id
        app.plan_name = plan_name

        self.ids.lbl_plan_name.text = (
            f"แผนตรวจนับ: {plan_code}"
        )

        self.ids.lbl_plan_detail.text = ""

        # -------------------------------------------------
        # Plan Empty
        # -------------------------------------------------
        if status == "PLAN_EMPTY" or total_items <= 0:

            self.ids.lbl_status.text = (
                "พบ Plan แต่ยังไม่มีรายการสินค้า"
            )

            self.set_count_enabled(False)
            return

        # -------------------------------------------------
        # Ready
        # -------------------------------------------------
        self.set_count_enabled(True)

        self.reset_location(
            show_message=False
        )

        self.ids.lbl_status.text = (
            "ข้อมูลพร้อมตรวจนับ "
            "กรุณายิง Location"
        )

        self.load_recent_counts()
        self._reset_scan_field()

    # =====================================================
    # Fallback Current Plan
    # ใช้กรณี Service ยังไม่มี get_current_plan()
    # =====================================================
    def _get_current_plan_fallback(self):

        app = App.get_running_app()

        sql = """
        SELECT
            p.plan_id,
            p.plan_code,
            p.plan_name,
            p.status,
            p.download_status,
            p.download_date,
            COUNT(pd.plan_detail_id) AS total_items
        FROM tb_plan AS p
        LEFT JOIN tb_plan_detail AS pd
            ON pd.plan_id = p.plan_id
        GROUP BY
            p.plan_id,
            p.plan_code,
            p.plan_name,
            p.status,
            p.download_status,
            p.download_date
        ORDER BY
            p.download_date DESC,
            p.plan_id DESC
        LIMIT 1
        """

        plan = app.db.query_one(
            sql
        )

        if not plan:

            return {
                "status": "NO_PLAN",
                "message": (
                    "ยังไม่มีแผนตรวจนับในเครื่อง"
                )
            }

        total_items = self._row_value(
            plan,
            "total_items",
            0
        )

        if not total_items:

            return {
                "status": "PLAN_EMPTY",
                "message": (
                    "พบ Plan แต่ยังไม่มีรายละเอียด"
                ),
                "plan": plan
            }

        return {
            "status": "READY",
            "message": "ข้อมูลพร้อมตรวจนับ",
            "plan": plan
        }

    # =====================================================
    # Enable / Disable Count Controls
    # =====================================================
    def set_count_enabled(self, enabled):

        enabled = bool(enabled)

        self.ids.txt_barcode.disabled = not enabled
        self.ids.txt_qty.disabled = not enabled
        self.ids.btn_calculator.disabled = not enabled
        self.ids.btn_change_location.disabled = (
            not enabled
        )

        # เปิดเมื่อพบสินค้าแล้วเท่านั้น
        self.ids.btn_save.disabled = True

    # =====================================================
    # Process Scan
    # =====================================================
    def process_scan(self, scan_value):
        """
        ลำดับการ Scan

        1. ถ้ายังไม่มี Location:
           ตรวจ Barcode เป็น Location

        2. ถ้ามี Location แล้ว:
           ตรวจ Barcode เป็นสินค้า
        """

        if self._is_processing:
            return

        scan_value = str(
            scan_value or ""
        ).strip()

        self.ids.txt_barcode.text = ""

        if not self.current_plan:

            self.ids.lbl_status.text = (
                "ยังไม่มี Plan ที่พร้อมตรวจนับ"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if not scan_value:

            self.ids.lbl_status.text = (
                "กรุณายิง Barcode"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        self._is_processing = True

        try:

            if not self.current_location:

                self.scan_location(
                    scan_value
                )

            else:

                self.scan_item(
                    scan_value
                )

        except ValueError as error:

            self.ids.lbl_status.text = str(error)
            self.play_error_sound()
            self._reset_scan_field()

        except Exception as error:

            self.ids.lbl_status.text = (
                f"เกิดข้อผิดพลาด: {error}"
            )
            self.play_error_sound()

            self._reset_scan_field()

        finally:

            self._is_processing = False

    # =====================================================
    # Scan Location
    # =====================================================
    def scan_location(self, location_code):
        
        location_code = str(
            location_code or ""
        ).strip()

        if not location_code:

            self.ids.lbl_status.text = (
                "กรุณายิง Barcode Location"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if not self.current_plan:

            self.ids.lbl_status.text = (
                "ยังไม่มี Plan ที่พร้อมตรวจนับ"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        plan_id = self._row_value(
            self.current_plan,
            "plan_id"
        )

        app = App.get_running_app()

        service = CountService(
            app.db
        )

        try:

            location = service.find_location(
                plan_id,
                location_code
            )

        except Exception as error:

            self.current_location = None

            self.ids.lbl_location.text = (
                "กรุณายิง Barcode Location"
            )

            self.ids.lbl_status.text = (
                f"ค้นหา Location ไม่สำเร็จ: {error}"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if not location:

            self.current_location = None

            self.ids.lbl_location.text = (
                "กรุณายิง Barcode Location"
            )

            self.ids.lbl_status.text = (
                f"ไม่พบ Location: {location_code} "
                f"ใน Plan {plan_id}"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        location_id = self._row_value(
            location,
            "location_id"
        )

        try:
            location_id = int(location_id)
        except (TypeError, ValueError):
            location_id = 0

        if location_id <= 0:
            self.current_location = None
            self.current_location_data = None
            self.ids.lbl_status.text = (
                "Location ไม่มี Server ID กรุณาล้างข้อมูลในเครื่อง "
                "แล้ว Download Plan ใหม่"
            )
            self.play_error_sound()
            self._reset_scan_field()
            return

        location_code_db = self._row_value(
            location,
            "location_code",
            ""
        )

        location_name = self._row_value(
            location,
            "location_name",
            ""
        )

        # เก็บ location_id สำหรับใช้บันทึก
        self.current_location = location_id

        # เก็บข้อมูลเต็ม เผื่อใช้ภายหลัง
        self.current_location_data = location

        # หน้าจอต้องแสดง Location Code ไม่ใช่ Location ID
        location_text = str(location_code_db or location_name or location_code).strip()

        self.ids.lbl_location.text = location_text

        self.ids.btn_change_location.disabled = False

        self.ids.lbl_status.text = (
            "พบ Location แล้ว "
            "กรุณายิง Barcode สินค้า"
        )

        self.current_item = None

        self._clear_item_display()

        self.ids.txt_qty.text = ""

        self._reset_scan_field()
    # =====================================================
    # Scan Item
    # =====================================================
    def scan_item(self, barcode):

        if not self.current_plan:

            self.ids.lbl_status.text = (
                "ยังไม่มี Plan ที่พร้อมตรวจนับ"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if not self.current_location:

            self.ids.lbl_status.text = (
                "กรุณายิง Location ก่อน"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        barcode = str(
            barcode or ""
        ).strip()

        if not barcode:

            self.ids.lbl_status.text = (
                "กรุณายิง Barcode สินค้า"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        app = App.get_running_app()
        service = CountService(app.db)

        plan_id = self._row_value(
            self.current_plan,
            "plan_id"
        )

        try:

            result = service.prepare_item(
                plan_id=plan_id,
                location_id=self.current_location,
                barcode=barcode
            )

        except AttributeError:

            # รองรับ CountService เวอร์ชันที่มี
            # find_item() และ get_plan_detail()
            result = self._prepare_item_fallback(
                service=service,
                plan_id=plan_id,
                location_id=self.current_location,
                barcode=barcode
            )

        status = result.get("status")

        if status == "ITEM_NOT_FOUND":

            self.current_item = None
            self._clear_item_display()

            self.ids.lbl_status.text = (
                f"ไม่พบสินค้า: {barcode}"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if status == "UNEXPECTED_ITEM":

            self.current_item = None
            self._clear_item_display()

            self.ids.lbl_status.text = (
                "สินค้านี้ไม่มีใน Plan "
                "หรือไม่อยู่ใน Location นี้"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if status != "READY":

            self.current_item = None
            self._clear_item_display()

            self.ids.lbl_status.text = (
                result.get(
                    "message",
                    status or "ไม่สามารถอ่านสินค้าได้"
                )
            )

            self._reset_scan_field()
            return

        item = result.get("item")
        detail = result.get("detail")

        if not item or not detail:

            self.current_item = None
            self._clear_item_display()

            self.ids.lbl_status.text = (
                "ข้อมูลสินค้าไม่สมบูรณ์"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        self.current_item = {
            "item": item,
            "detail": detail,
            "barcode": barcode
        }

        item_code = self._row_value(
            item,
            "item_code",
            "-"
        )

        item_name = self._row_value(
            item,
            "item_name",
            "-"
        )

        uom = self._row_value(
            item,
            "uom",
            "-"
        ) or "-"

        self.ids.lbl_item_code.text = (
            f"รหัสสินค้า: {item_code}"
        )

        self.ids.lbl_item_name.text = (
            f"ชื่อสินค้า: {item_name}"
        )

        self.ids.lbl_unit.text = (
            f"หน่วย: {uom}"
        )

        self.ids.txt_qty.text = ""
        self.ids.btn_save.disabled = False

        self.ids.lbl_status.text = (
            "พบสินค้า กรุณาระบุจำนวนแล้วกดบันทึก"
        )

        Clock.schedule_once(
            self._focus_qty,
            0.1
        )

    # =====================================================
    # Prepare Item Fallback
    # =====================================================
    def _prepare_item_fallback(
        self,
        service,
        plan_id,
        location_id,
        barcode
    ):

        item = service.count_repo.find_item(
            barcode
        )

        if not item:

            return {
                "status": "ITEM_NOT_FOUND"
            }

        item_id = self._row_value(
            item,
            "item_id"
        )

        detail = service.count_repo.get_plan_detail(
            plan_id,
            item_id,
            location_id
        )

        if not detail:

            return {
                "status": "UNEXPECTED_ITEM",
                "item": item
            }

        return {
            "status": "READY",
            "item": item,
            "detail": detail
        }

    # =====================================================
    # Save Current Item
    # =====================================================
    def save_current_item(self):

        if self._is_processing:
            return

        if not self.current_plan:

            self.ids.lbl_status.text = (
                "ยังไม่มี Plan ที่พร้อมตรวจนับ"
            )
            self.play_error_sound()
            return

        if not self.current_location:

            self.ids.lbl_status.text = (
                "กรุณายิง Location ก่อน"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        if not self.current_item:

            self.ids.lbl_status.text = (
                "กรุณายิง Barcode สินค้าก่อน"
            )
            self.play_error_sound()

            self._reset_scan_field()
            return

        qty_text = str(
            self.ids.txt_qty.text or ""
        ).strip()

        if not qty_text:

            self.ids.lbl_status.text = (
                "กรุณาระบุจำนวน"
            )
            self.play_error_sound()

            Clock.schedule_once(
                self._focus_qty,
                0.1
            )
            return

        try:

            qty = float(
                qty_text
            )

        except (TypeError, ValueError):

            self.ids.lbl_status.text = (
                "จำนวนไม่ถูกต้อง"
            )
            self.play_error_sound()

            Clock.schedule_once(
                self._focus_qty,
                0.1
            )
            return

        if qty < 0:

            self.ids.lbl_status.text = (
                "จำนวนต้องไม่ติดลบ"
            )
            self.play_error_sound()

            Clock.schedule_once(
                self._focus_qty,
                0.1
            )
            return

        app = App.get_running_app()

        checker = str(
            getattr(app, "device_name", "")
            or getattr(Config, "DEVICE_NAME", "")
            or ""
        ).strip()

        if not checker:
            checker = "UNKNOWN_DEVICE"

        # บังคับให้ค่าบนหน้าจอตรงกับ App
        self.ids.txt_checker.text = checker

        plan_id = self._row_value(
            self.current_plan,
            "plan_id"
        )

        item = self.current_item["item"]
        detail = self.current_item["detail"]
        barcode = self.current_item["barcode"]

        item_id = self._row_value(
            item,
            "item_id"
        )

        plan_detail_id = self._row_value(
            detail,
            "plan_detail_id"
        )

        self._is_processing = True
        self.ids.btn_save.disabled = True

        try:

            service = CountService(
                app.db
            )

            result = service.save_count(
                plan_id=plan_id,
                plan_detail_id=plan_detail_id,
                item_id=item_id,
                location_id=self.current_location,
                barcode=barcode,
                qty=qty,
                checker=checker
            )

            if not result.get(
                "success",
                False
            ):

                raise ValueError(
                    result.get(
                        "message",
                        "ไม่สามารถบันทึกข้อมูลได้"
                    )
                )

            item_name = self._row_value(
                item,
                "item_name",
                ""
            )

            self.ids.lbl_status.text = (
                f"บันทึกสำเร็จ: "
                f"{item_name} จำนวน {qty:g}"
            )

            self.current_item = None
            self._clear_item_display()

            self.ids.txt_qty.text = ""

            self.load_recent_counts()
            self._reset_scan_field()

        except Exception as error:

            self.ids.lbl_status.text = (
                f"บันทึกไม่สำเร็จ: {error}"
            )
            self.play_error_sound()

            self.ids.btn_save.disabled = False

        finally:

            self._is_processing = False

    # =====================================================
    # Reset / Change Location
    # =====================================================
    def reset_location(
        self,
        show_message=True
    ):

        self.current_location = None
        self.current_location_data = None
        self.current_item = None

        self.ids.lbl_location.text = (
            "กรุณายิง Barcode Location"
        )

        self.ids.txt_qty.text = ""

        self._clear_item_display()

        self.ids.btn_save.disabled = True

        # ปุ่มเปลี่ยน Location ยังเปิดไว้ได้
        # เมื่อ Plan พร้อม
        self.ids.btn_change_location.disabled = (
            self.current_plan is None
        )

        if show_message:

            self.ids.lbl_status.text = (
                "เปลี่ยน Location "
                "กรุณายิง Barcode Location ใหม่"
            )

        self._reset_scan_field()

    # =====================================================
    # Load Recent Counts
    # =====================================================
    def load_recent_counts(self):
        """อ่าน 15 รายการล่าสุดจาก SQLite ทุกครั้ง ไม่ใช้ข้อมูลค้างในหน้าจอ"""
        self.ids.recent_list.clear_widgets()
        self._update_correction_mode_ui()

        if not self.current_plan:
            return

        app = App.get_running_app()
        plan_id = self._row_value(self.current_plan, "plan_id")

        try:
            service = CountService(app.db)
            rows = service.get_recent_counts(plan_id, limit=15)
        except Exception as error:
            self.ids.lbl_status.text = f"อ่านรายการล่าสุดไม่ได้: {error}"
            self.play_error_sound()
            return

        if not rows:
            self.ids.recent_list.add_widget(
                Button(
                    text="ยังไม่มีรายการตรวจนับ",
                    font_name="ThaiFont",
                    font_size="15sp",
                    size_hint_y=None,
                    height="36dp",
                    disabled=True,
                    background_normal="",
                    background_disabled_normal="",
                    background_color=(1, 1, 1, 1),
                    color=(0.35, 0.35, 0.35, 1),
                    halign="left",
                    valign="middle",
                )
            )
            return

        valid_history_ids = set()

        for index, source_row in enumerate(rows):
            row = dict(source_row) if not isinstance(source_row, dict) else dict(source_row)
            history_id = self._row_value(row, "history_id")
            valid_history_ids.add(history_id)

            item_code = self._row_value(row, "item_code", "-")
            qty = self._row_value(row, "qty", 0)
            uom = self._row_value(row, "uom", "") or "-"
            location_code = self._row_value(row, "location_code", "-")

            try:
                qty_text = f"{float(qty):g}"
            except (TypeError, ValueError):
                qty_text = str(qty)

            # ตัดชื่อสินค้าออกเพื่อให้เห็น LOC / Item / Qty ครบในจอเล็ก
            prefix = "[เลือก] " if history_id in self.selected_recent_rows else ""
            text = f"{prefix}{location_code} | {item_code} | {qty_text} {uom}".strip()

            if history_id in self.selected_recent_rows:
                background = (1.0, 0.82, 0.45, 1)
            elif index % 2 == 0:
                background = (1, 1, 1, 1)
            else:
                background = (0.96, 0.96, 0.96, 1)

            list_item = Button(
                text=text,
                font_name="ThaiFont",
                font_size="14sp",
                size_hint_y=None,
                height="36dp",
                background_normal="",
                background_down="",
                background_color=background,
                color=(0.10, 0.10, 0.10, 1),
                halign="left",
                valign="middle",
                shorten=True,
                shorten_from="right",
            )
            list_item.bind(
                width=lambda instance, width: setattr(
                    instance, "text_size", (max(width - 12, 0), instance.height)
                )
            )
            list_item.bind(
                on_release=lambda instance, data=row: self.select_recent_count(data)
            )
            self.ids.recent_list.add_widget(list_item)

        self.selected_recent_rows = {
            key: value
            for key, value in self.selected_recent_rows.items()
            if key in valid_history_ids
        }
        self._update_location_selection_buttons()

        if "recent_scroll" in self.ids:
            self.ids.recent_scroll.scroll_y = 1

    def select_recent_count(self, row):
        """เลือกข้อมูลตาม Mode ที่กำหนดจาก Tab ล่าสุด"""
        if not row:
            return

        row = dict(row)
        history_id = self._row_value(row, "history_id")

        # Mode LOCATION: เลือกได้หลายรายการ และยังไม่เปิด Correction ทันที
        if self.correction_selection_mode == "LOCATION":
            if history_id in self.selected_recent_rows:
                self.selected_recent_rows.pop(history_id, None)
            else:
                self.selected_recent_rows[history_id] = row
            self._update_correction_mode_ui()
            self.load_recent_counts()
            return

        # Mode QTY: แตะหนึ่งรายการแล้วเปิดหน้าแก้จำนวนทันที
        self._clear_correction_selection_state(clear_mode=False)
        app = App.get_running_app()
        app.correction_mode = "QTY"
        app.selected_count_transaction = row
        app.selected_count_transactions = None

        if self.manager and self.manager.has_screen("correction"):
            correction_screen = self.manager.get_screen("correction")
            correction_screen.open_for_qty(row)
            self.manager.current = "correction"
        else:
            self.ids.lbl_status.text = "ไม่พบหน้าจอแก้ไข"
            self.play_error_sound()

    def switch_correction_mode(self):
        """สลับ Mode ที่ Tab ล่าสุด และล้าง State ของ Mode เดิมทั้งหมด"""
        new_mode = (
            "LOCATION"
            if self.correction_selection_mode == "QTY"
            else "QTY"
        )
        self.set_correction_mode(new_mode)

    def set_correction_mode(self, mode):
        mode = str(mode or "QTY").upper()
        if mode not in ("QTY", "LOCATION"):
            mode = "QTY"

        self._clear_correction_selection_state(clear_mode=False)
        self.correction_selection_mode = mode
        self.location_selection_mode = mode == "LOCATION"

        app = App.get_running_app()
        app.correction_mode = mode

        if mode == "QTY":
            self.ids.lbl_status.text = "โหมดแก้จำนวน: แตะ 1 รายการ"
        else:
            self.ids.lbl_status.text = "โหมดแก้ Location: เลือกได้หลายรายการ"

        self._update_correction_mode_ui()
        self.load_recent_counts()

    def _clear_correction_selection_state(self, clear_mode=False):
        self.selected_recent_rows = {}

        app = App.get_running_app()
        app.selected_count_transaction = None
        app.selected_count_transactions = None

        if clear_mode:
            self.correction_selection_mode = "QTY"
            self.location_selection_mode = False
            app.correction_mode = "QTY"

    # รองรับชื่อ Method เดิมจาก KV/โค้ดเก่า
    def toggle_location_selection(self):
        self.switch_correction_mode()

    def open_location_correction(self):
        if self.correction_selection_mode != "LOCATION":
            self.ids.lbl_status.text = "กรุณาเปลี่ยนเป็นโหมดแก้ Location ก่อน"
            self.play_error_sound()
            return

        if not self.selected_recent_rows:
            self.ids.lbl_status.text = "กรุณาเลือกรายการที่ต้องการเปลี่ยน Location"
            self.play_error_sound()
            return

        rows = list(self.selected_recent_rows.values())
        app = App.get_running_app()
        app.correction_mode = "LOCATION"
        app.selected_count_transaction = None
        app.selected_count_transactions = rows

        if self.manager and self.manager.has_screen("correction"):
            correction_screen = self.manager.get_screen("correction")
            correction_screen.open_for_location(rows)
            self.manager.current = "correction"
        else:
            self.ids.lbl_status.text = "ไม่พบหน้าจอแก้ไข"
            self.play_error_sound()

    def _update_correction_mode_ui(self):
        is_location = self.correction_selection_mode == "LOCATION"
        total = len(self.selected_recent_rows)

        if "recent_mode_card" in self.ids:
            self.ids.recent_mode_card.md_bg_color = (
                (1.0, 0.93, 0.82, 1)
                if is_location
                else (0.88, 1.0, 0.90, 1)
            )

        if "lbl_recent_mode" in self.ids:
            self.ids.lbl_recent_mode.text = (
                "MODE: แก้ LOCATION (เลือกหลายรายการ)"
                if is_location
                else "MODE: แก้จำนวน (เลือก 1 รายการ)"
            )
            self.ids.lbl_recent_mode.text_color = (
                (0.85, 0.35, 0.05, 1)
                if is_location
                else (0.05, 0.55, 0.20, 1)
            )

        if "btn_location_mode" in self.ids:
            self.ids.btn_location_mode.text = (
                "เปลี่ยนเป็นแก้จำนวน"
                if is_location
                else "เปลี่ยนเป็นแก้ LOC"
            )
            self.ids.btn_location_mode.md_bg_color = (
                (0.05, 0.55, 0.20, 1)
                if is_location
                else (0.95, 0.45, 0.05, 1)
            )

        if "btn_apply_location" in self.ids:
            self.ids.btn_apply_location.text = f"ยืนยัน ({total})"
            self.ids.btn_apply_location.disabled = not is_location or total == 0
            self.ids.btn_apply_location.opacity = 1 if is_location else 0
            self.ids.btn_apply_location.width = "96dp" if is_location else "0dp"

    # รองรับชื่อ Method เดิม
    def _update_location_selection_buttons(self):
        self._update_correction_mode_ui()

    # =====================================================
    # Switch Count / Recent / Sync Tab
    # =====================================================
    def switch_tab(self, tab_name):

        if tab_name not in (
            "count_tab",
            "recent_tab",
            "sync_tab",
        ):
            return

        self.ids.count_tab_manager.current = tab_name
        self._set_active_tab(tab_name)

        if tab_name == "recent_tab":
            self.load_recent_counts()
            return

        if tab_name == "sync_tab":
            self.load_sync_status()
            return

        Clock.schedule_once(
            lambda dt: self._reset_scan_field(),
            0.05
        )

    def _set_active_tab(self, tab_name):
        """กำหนดสถานะปุ่ม Tab โดยไม่ซ่อนหรือเปิด Screen อื่น"""
        if "tab_count" in self.ids:
            self.ids.tab_count.disabled = tab_name == "count_tab"
        if "tab_recent" in self.ids:
            self.ids.tab_recent.disabled = tab_name == "recent_tab"
        if "tab_sync" in self.ids:
            self.ids.tab_sync.disabled = tab_name == "sync_tab"

    # =====================================================
    # Sync Tab
    # =====================================================
    def _sync_context(self):
        if not self.current_plan:
            raise ValueError("ไม่พบ Plan ที่กำลังใช้งาน")
        app = App.get_running_app()
        plan_id = int(self._row_value(self.current_plan, "plan_id", 0) or 0)
        if plan_id <= 0:
            raise ValueError("Plan ID ไม่ถูกต้อง")
        device_name = str(
            getattr(app, "device_name", "")
            or getattr(Config, "DEVICE_NAME", "")
            or "UNKNOWN_DEVICE"
        ).strip()
        sync_url = str(
            getattr(app, "sync_url", "")
            or getattr(app, "api_url", "")
            or ""
        ).strip()
        timeout = int(getattr(app, "timeout", 120) or 120)
        batch_size = int(getattr(app, "sync_batch", 500) or 500)
        return app, plan_id, device_name, sync_url, timeout, batch_size

    def load_sync_status(self):
        """Read GetSyncStatus once per user action; never poll continuously."""
        if self._sync_status_in_flight or self._is_processing:
            return
        if not self.current_plan:
            self.ids.lbl_local_summary.text = "รอส่ง 0   ส่งแล้ว 0   ผิดพลาด 0"
            self.ids.lbl_server_summary.text = "รอ Process 0   สำเร็จ 0   ผิดพลาด 0"
            self.ids.lbl_sync_status.text = "ยังไม่มีข้อมูล Sync"
            self.ids.btn_sync_now.disabled = True
            self.ids.btn_retry_sync.disabled = True
            self.ids.btn_process_server.disabled = True
            return
        if "count_tab_manager" in self.ids and self.ids.count_tab_manager.current != "sync_tab":
            return
        self._sync_status_in_flight = True
        try:
            app, plan_id, device_name, sync_url, timeout, batch_size = self._sync_context()
            service = SyncService(app.db, timeout)
            local = service.local_summary(plan_id, "COUNT")

            self._local_sync_summary = {
                "PENDING": int(local.get("PENDING", 0) or 0),
                "SYNCING": int(local.get("SYNCING", 0) or 0),
                "SYNCED": int(local.get("SYNCED", 0) or 0),
                "ERROR": int(local.get("ERROR", 0) or 0),
            }
            # ระหว่างรอผลจาก Server ยังไม่ทราบว่ามีรายการรอ Process หรือไม่
            self._server_sync_summary = {
                "WAITING": 0,
                "PROCESSING": 0,
                "SUCCESS": 0,
                "ERROR": 0,
                "LOADED": False,
            }
            self._update_sync_button_states()

            plan_code = self._row_value(self.current_plan, "plan_code", "") or self._row_value(self.current_plan, "plan_details", "") or "-"
            self.ids.lbl_sync_device.text = f"{device_name} | Plan {plan_code}"
            self.ids.lbl_sync_plan.text = ""
            self.ids.lbl_local_summary.text = (
                f"รอส่ง {self._local_sync_summary['PENDING']}   "
                f"ส่งแล้ว {self._local_sync_summary['SYNCED']}   "
                f"ผิดพลาด {self._local_sync_summary['ERROR']}"
            )
            local_total = sum(self._local_sync_summary.values())
            if local_total <= 0:
                self._sync_status_in_flight = False
                self.ids.lbl_server_summary.text = "รอ Process 0   สำเร็จ 0   ผิดพลาด 0"
                self.ids.lbl_sync_status.text = "ยังไม่มีข้อมูล Sync"
                self._update_sync_button_states()
                return

            self.ids.lbl_sync_status.text = "กำลังอ่านสถานะ Server..."

            self._run_sync_worker(
                lambda: service.server_status(sync_url, plan_id, "COUNT"),
                self._apply_server_status,
                "อ่านสถานะ Server",
            )
        except Exception as error:
            self._sync_status_in_flight = False
            self.ids.lbl_sync_status.text = f"อ่านสถานะ Sync ไม่ได้: {error}"
            self.play_error_sound()

    def start_sync(self):
        """ส่ง PENDING ของ Plan และ Device นี้เข้า Staging"""
        try:
            app, plan_id, device_name, sync_url, timeout, batch_size = self._sync_context()
            service = SyncService(app.db, timeout)
            self.ids.lbl_sync_status.text = "กำลังส่งข้อมูลขึ้น Server..."
            self._run_sync_worker(
                lambda: service.send(
                    sync_url, plan_id, device_name,
                    getattr(Config, "APP_VERSION", "1.0.0"), batch_size,
                    transaction_type="COUNT",
                ),
                self._after_send,
                "ส่งข้อมูล",
            )
        except Exception as error:
            self.ids.lbl_sync_status.text = f"ส่งข้อมูลไม่ได้: {error}"
            self.play_error_sound()

    def retry_sync(self):
        """ส่ง PENDING และ ERROR ใหม่"""
        try:
            app, plan_id, device_name, sync_url, timeout, batch_size = self._sync_context()
            service = SyncService(app.db, timeout)
            self.ids.lbl_sync_status.text = "กำลังส่งรายการ Error ใหม่..."
            self._run_sync_worker(
                lambda: service.retry_error(
                    sync_url, plan_id, device_name,
                    getattr(Config, "APP_VERSION", "1.0.0"), batch_size,
                    transaction_type="COUNT",
                ),
                self._after_send,
                "Retry",
            )
        except Exception as error:
            self.ids.lbl_sync_status.text = f"Retry ไม่ได้: {error}"
            self.play_error_sound()

    def process_server_data(self):
        """Process เฉพาะ Batch ล่าสุดของ Device และ Plan นี้"""
        try:
            app, plan_id, device_name, sync_url, timeout, batch_size = self._sync_context()
            service = SyncService(app.db, timeout)
            self.ids.lbl_sync_status.text = "กำลัง Process ข้อมูลของเครื่องนี้..."
            self._run_sync_worker(
                lambda: service.process(sync_url, plan_id, device_name, "COUNT"),
                self._after_process,
                "Process",
            )
        except Exception as error:
            self.ids.lbl_sync_status.text = f"Process ไม่ได้: {error}"
            self.play_error_sound()

    def _run_sync_worker(self, work, on_success, action_name):
        if self._is_processing:
            return
        self._is_processing = True
        self._set_sync_buttons(False)

        def runner():
            try:
                result = work()
                Clock.schedule_once(lambda dt: self._sync_worker_success(on_success, result), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda dt, err=str(exc): self._sync_worker_error(action_name, err), 0
                )

        threading.Thread(target=runner, daemon=True).start()

    def _sync_worker_success(self, callback, result):
        self._is_processing = False
        callback(result)
        self._update_sync_button_states()

    def _sync_worker_error(self, action_name, message):
        self._is_processing = False
        if action_name == "อ่านสถานะ Server":
            self._sync_status_in_flight = False
        self.ids.lbl_sync_status.text = f"{action_name} ไม่สำเร็จ: {message}"
        self._update_sync_button_states()
        self.play_error_sound()

    def _after_send(self, result):
        if result.get("status") == "NO_DATA":
            self.ids.lbl_sync_status.text = "ไม่มีข้อมูลในเครื่องที่รอส่ง"
        else:
            self.ids.lbl_sync_status.text = (
                f"ส่งสำเร็จ {int(result.get('success', 0) or 0)} รายการ"
                if int(result.get("error", 0) or 0) == 0
                else (
                    f"ส่งสำเร็จ {int(result.get('success', 0) or 0)} | "
                    f"ผิดพลาด {int(result.get('error', 0) or 0)}"
                )
            )
        self.load_sync_status()

    def _after_process(self, result):
        processed = int(result.get("processed", result.get("success_count", 0)) or 0)
        self.ids.lbl_sync_status.text = f"Process สำเร็จ {processed} รายการ"
        self.load_sync_status()

    def _apply_server_status(self, result):
        """Apply one GetSyncStatus response without starting another request."""
        self._sync_status_in_flight = False
        waiting = int(result.get("waiting_count", result.get("waiting", 0)) or 0)
        processing = int(result.get("processing_count", result.get("processing", 0)) or 0)
        success_count = int(
            result.get("success_count", result.get("processed_success", 0)) or 0
        )
        error_count = int(
            result.get("error_count", result.get("processed_error", 0)) or 0
        )

        self.ids.lbl_server_summary.text = (
            f"รอ Process {waiting}   สำเร็จ {success_count}   ผิดพลาด {error_count}"
        )

        self._server_sync_summary = {
            "WAITING": waiting,
            "PROCESSING": processing,
            "SUCCESS": success_count,
            "ERROR": error_count,
            "LOADED": True,
        }

        has_batch = bool(result.get("has_batch"))
        local = getattr(self, "_local_sync_summary", {}) or {}
        local_pending = int(local.get("PENDING", 0) or 0)
        local_syncing = int(local.get("SYNCING", 0) or 0)

        if not has_batch:
            if local_syncing > 0:
                status_text = "กำลังส่งข้อมูล"
            elif local_pending > 0:
                status_text = "ยังไม่ได้ส่งข้อมูล"
            else:
                status_text = "ยังไม่มีข้อมูลสำหรับ Sync"
        elif error_count > 0:
            status_text = f"Process ผิดพลาด {error_count} รายการ"
        elif processing > 0:
            status_text = f"กำลัง Process {processing} รายการ"
        elif waiting > 0:
            status_text = f"ส่งแล้ว รอ Process {waiting} รายการ"
        elif success_count > 0:
            status_text = f"Process สำเร็จ {success_count} รายการ"
        else:
            status_text = result.get("status_message") or "พร้อมใช้งาน"

        self.ids.lbl_sync_status.text = status_text
        self._update_sync_button_states()

    def _update_sync_button_states(self):
        """เปิดปุ่มเฉพาะเมื่อมีงานที่ปุ่มนั้นสามารถทำได้จริง"""
        if self._is_processing:
            self._set_sync_buttons(False)
            return

        local = getattr(self, "_local_sync_summary", {}) or {}
        server = getattr(self, "_server_sync_summary", {}) or {}

        pending = int(local.get("PENDING", 0) or 0)
        syncing = int(local.get("SYNCING", 0) or 0)
        local_error = int(local.get("ERROR", 0) or 0)
        waiting = int(server.get("WAITING", 0) or 0)
        processing = int(server.get("PROCESSING", 0) or 0)
        server_loaded = bool(server.get("LOADED", False))

        if "btn_sync_now" in self.ids:
            self.ids.btn_sync_now.disabled = pending <= 0 or syncing > 0

        if "btn_retry_sync" in self.ids:
            self.ids.btn_retry_sync.disabled = local_error <= 0 or syncing > 0

        if "btn_process_server" in self.ids:
            self.ids.btn_process_server.disabled = (
                not server_loaded or waiting <= 0 or processing > 0
            )

        if "btn_refresh_sync" in self.ids:
            self.ids.btn_refresh_sync.disabled = False

    def _set_sync_buttons(self, enabled):
        for widget_id in (
            "btn_sync_now", "btn_process_server", "btn_retry_sync", "btn_refresh_sync"
        ):
            if widget_id in self.ids:
                self.ids[widget_id].disabled = not enabled

    # =====================================================
    # Open Device Calculator
    # =====================================================
    def open_calculator(self):

        try:

            # ---------------------------------------------
            # Windows
            # ---------------------------------------------
            if platform == "win":

                subprocess.Popen(
                    ["calc.exe"]
                )
                return

            # ---------------------------------------------
            # Android
            # ---------------------------------------------
            if platform == "android":

                # Import เฉพาะตอนรัน Android
                # Pylance บน Windows อาจยังแสดง Warning
                # แต่ไม่มีผลต่อการ Build Android
                from jnius import autoclass  # type: ignore

                PythonActivity = autoclass(
                    "org.kivy.android.PythonActivity"
                )

                Intent = autoclass(
                    "android.content.Intent"
                )

                activity = (
                    PythonActivity.mActivity
                )

                # วิธีมาตรฐาน: ขอเปิด App Calculator
                try:

                    intent = (
                        Intent.makeMainSelectorActivity(
                            Intent.ACTION_MAIN,
                            "android.intent.category.APP_CALCULATOR"
                        )
                    )

                    activity.startActivity(
                        intent
                    )
                    return

                except Exception:
                    pass

                # Fallback Package ที่พบบ่อย
                package_names = [
                    "com.google.android.calculator",
                    "com.android.calculator2",
                    "com.sec.android.app.popupcalculator",
                    "com.miui.calculator",
                    "com.oneplus.calculator"
                ]

                package_manager = (
                    activity.getPackageManager()
                )

                for package_name in package_names:

                    intent = (
                        package_manager
                        .getLaunchIntentForPackage(
                            package_name
                        )
                    )

                    if intent:

                        activity.startActivity(
                            intent
                        )
                        return

                self.ids.lbl_status.text = (
                    "ไม่พบ App เครื่องคิดเลขในเครื่อง"
                )
                self.play_error_sound()
                return

            self.ids.lbl_status.text = (
                "ระบบปฏิบัติการนี้ไม่รองรับ "
                "การเปิดเครื่องคิดเลข"
            )

        except Exception as error:

            self.ids.lbl_status.text = (
                f"เปิดเครื่องคิดเลขไม่ได้: {error}"
            )
            self.play_error_sound()

    # =====================================================
    # Go Back
    # =====================================================
    def go_back(self):
        """จาก Tab ล่าสุด/Sync กลับ Tab นับสินค้า; จาก Tab นับสินค้าไป Main Menu"""
        current_tab = "count_tab"
        if "count_tab_manager" in self.ids:
            current_tab = self.ids.count_tab_manager.current

        if current_tab != "count_tab":
            self.switch_tab("count_tab")
            return

        self.current_item = None
        self.current_location = None

        if not self.manager:
            return

        for screen_name in ("main_menu", "main_menu_screen", "menu_screen", "home"):
            if self.manager.has_screen(screen_name):
                self.manager.current = screen_name
                return

        self.ids.lbl_status.text = "ไม่พบหน้าจอ Main Menu"
        self.play_error_sound()

    # =====================================================
    # Clear Item Display
    # =====================================================
    def _clear_item_display(self):

        self.ids.lbl_item_code.text = (
            "รหัสสินค้า: -"
        )

        self.ids.lbl_item_name.text = (
            "ชื่อสินค้า: -"
        )

        self.ids.lbl_unit.text = "หน่วย: -"

        self.ids.btn_save.disabled = True

    # =====================================================
    # Reset Barcode Field
    # =====================================================
    def _reset_scan_field(self):

        self.ids.txt_barcode.text = ""

        Clock.schedule_once(
            self._focus_barcode,
            0.15
        )

    # =====================================================
    # Focus Barcode
    # =====================================================
    def _focus_barcode(self, dt):

        if self.ids.txt_barcode.disabled:
            return

        self.ids.txt_barcode.focus = False

        Clock.schedule_once(
            self._set_barcode_focus,
            0.05
        )

    def _set_barcode_focus(self, dt):

        if not self.ids.txt_barcode.disabled:
            self.ids.txt_barcode.focus = True

    # =====================================================
    # Focus Qty
    # =====================================================
    def _focus_qty(self, dt):

        if self.ids.txt_qty.disabled:
            return

        self.ids.txt_qty.focus = False

        Clock.schedule_once(
            self._set_qty_focus,
            0.05
        )

    def _set_qty_focus(self, dt):

        if not self.ids.txt_qty.disabled:
            self.ids.txt_qty.focus = True

    # =====================================================
    # Status / Error Sound
    # =====================================================
    def show_status(self, text, is_error=False):
        self.ids.lbl_status.text = str(text or "")
        if is_error:
            self.play_error_sound()

    def play_error_sound(self):
        try:
            if platform == "win":
                import winsound
                winsound.Beep(900, 450)
                return

            if platform == "android":
                from jnius import autoclass  # type: ignore
                ToneGenerator = autoclass("android.media.ToneGenerator")
                AudioManager = autoclass("android.media.AudioManager")
                tone = ToneGenerator(AudioManager.STREAM_ALARM, 100)
                tone.startTone(ToneGenerator.TONE_PROP_NACK, 500)
        except Exception:
            pass

    # =====================================================
    # Read sqlite3.Row / dict / object
    # =====================================================
    @staticmethod
    def _row_value(
        row,
        field_name,
        default=None
    ):

        if row is None:
            return default

        if isinstance(row, dict):
            return row.get(
                field_name,
                default
            )

        try:
            return row[field_name]
        except (
            KeyError,
            IndexError,
            TypeError
        ):
            pass

        return getattr(
            row,
            field_name,
            default
        )
