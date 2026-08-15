from __future__ import annotations

import threading
import requests
from functools import partial
from kivy.app import App
from kivy.utils import platform
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.factory import Factory
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import BooleanProperty, StringProperty
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from screens.base_screen import BaseScreen
from countstock import database
from countstock.sound import play_notification

API_ROOT = "/API_HWK_CountStock_Data"


class RecentClickableLabel(ButtonBehavior, MDLabel):
    """Lightweight Recent cell; tap any cell in a row to select it."""
    pass


class CountStockBaseScreen(BaseScreen):
    """Shared CountStock behavior without changing HWK Stock screens."""

    def show_error(self, text):
        play_notification(success=False)
        super().show_error(text)


class CountStockMenuScreen(CountStockBaseScreen):
    def go_launcher(self):
        self.manager.current = "launcher"

    def go_to(self, name):
        self.manager.current = name

    def exit_app(self):
        App.get_running_app().stop()


class CountStockConfigScreen(CountStockBaseScreen):
    menu = None
    selected = None

    def on_enter(self, *args):
        config = database.get_config()
        if config:
            self.ids.txt_iis_ip.text = config.get("iis_server_ip", "")
            self.ids.btn_branch.text = config.get("branch_name", "เลือกสาขา")
            self.ids.lbl_detail.text = self._detail(config)

    def go_back(self):
        self.manager.current = "countstock_menu"

    def fetch_config(self):
        iis_ip = self.ids.txt_iis_ip.text.strip()
        if not iis_ip:
            self.show_error("กรุณากรอก IIS Server IP")
            return
        self.show_loading("กำลังอ่าน config.ashx...")
        threading.Thread(target=self._fetch_worker, args=(iis_ip,), daemon=True).start()

    def _fetch_worker(self, iis_ip):
        try:
            response = requests.get(f"http://{iis_ip}{API_ROOT}/get_config.ashx", timeout=20)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("รูปแบบ config.ashx ไม่ถูกต้อง")
            branches = data.get("branches") or []
            staff_list = data.get("staff_list") or []
            if not branches:
                raise ValueError("config.ashx ไม่ส่งรายการสาขา")
            database.replace_staff(staff_list)
            Clock.schedule_once(lambda _dt: self._show_branches(branches))
        except Exception as exc:
            Clock.schedule_once(lambda _dt, e=str(exc): self._fetch_failed(e))

    def _fetch_failed(self, message):
        self.hide_loading()
        self.show_error(message)

    def _show_branches(self, branches):
        self.hide_loading()
        items = [{
            "text": str(item.get("branch_name", "-")),
            "viewclass": "OneLineListItem",
            "on_release": lambda item=item: self.select_branch(item),
        } for item in branches]
        self.menu = MDDropdownMenu(caller=self.ids.btn_branch, items=items, width_mult=4)
        self.menu.open()

    def select_branch(self, item):
        self.selected = item
        self.ids.btn_branch.text = str(item.get("branch_name", "-"))
        self.ids.lbl_detail.text = self._detail(item)
        if self.menu:
            self.menu.dismiss()

    def save(self):
        if not self.selected:
            self.show_error("กรุณาโหลด Config และเลือกสาขา")
            return
        database.save_config(self.selected, self.ids.txt_iis_ip.text.strip())
        self.show_success("บันทึก Config ของ CountStock แล้ว")

    @staticmethod
    def _detail(item):
        return f"DB: {item.get('db_name','-')}\nเดือน: {item.get('count_month','-')}"


class CountStockImportScreen(CountStockBaseScreen):
    def on_enter(self, *args):
        self.refresh_sqlite_count()

    def refresh_sqlite_count(self):
        stats = database.get_product_stats()
        self.ids.lbl_sqlite_count.text = (
            f"ข้อมูลใน SQLite\n"
            f"สินค้า {stats['product_count']:,} รายการ\n"
            f"บาร์โค้ด {stats['barcode_count']:,} รายการ"
        )

    def go_back(self):
        self.manager.current = "countstock_menu"

    def start_import(self):
        self.ids.btn_import.disabled = True
        self.ids.lbl_status.text = "กำลังนำเข้าข้อมูลสินค้า..."
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            config = database.get_config()
            if not config:
                raise ValueError("กรุณาตั้งค่า CountStock ก่อน")
            payload = {
                "db_server_ip": config.get("db_server_ip", ""),
                "db_name": config.get("db_name", ""),
                "month": config.get("count_month", ""),
            }
            url = f"http://{config['iis_server_ip']}{API_ROOT}/get_products.ashx"
            response = requests.post(url, json=payload, timeout=300)
            response.raise_for_status()
            count = database.replace_products(response.json())
            Clock.schedule_once(lambda _dt: self._done(f"นำเข้าแล้ว {count:,} รายการ"))
        except Exception as exc:
            Clock.schedule_once(lambda _dt, e=str(exc): self._failed(e))

    def _done(self, message):
        self.ids.btn_import.disabled = False
        self.ids.lbl_status.text = message
        self.refresh_sqlite_count()
        self.show_success(message)

    def _failed(self, message):
        self.ids.btn_import.disabled = False
        self.ids.lbl_status.text = "นำเข้าไม่สำเร็จ"
        self.show_error(message)


class CountStockScanScreen(CountStockBaseScreen):
    """CountStock scanner screen using one scanner TextField.

    Flow: Staff -> scan Location -> scan Barcode/Item Code continuously.
    """

    location_locked = BooleanProperty(False)
    current_location = StringProperty("")
    scan_guide_text = StringProperty("กรุณายิง LOCATION")
    scan_hint_text = StringProperty("ยิง LOCATION แล้วกด Enter")
    _dialog = None

    staff_menu = None
    selected_staff = ""

    def on_enter(self, *args):
        self._load_staff_dropdown()
        self._clear_product_display()
        self.refresh_recent()

        # เปิดหน้าจอใหม่ให้รอ Location ที่ช่อง Scan เดียว
        self.current_location = ""
        self.location_locked = False
        self._set_scan_mode_location()
        if "txt_scan" in self.ids:
            self.ids.txt_scan.text = ""
        Clock.schedule_once(lambda _dt: self._focus_scan(), 0.20)

    def go_back(self):
        self._dismiss_dialog()
        self.manager.current = "countstock_menu"

    # =====================================================
    # Staff
    # =====================================================
    def _load_staff_dropdown(self):
        staff_list = database.get_staff_list()
        if self.selected_staff not in staff_list:
            self.selected_staff = ""
        if "btn_staff" in self.ids:
            self.ids.btn_staff.text = self.selected_staff or "-เลือก-"

    def open_staff_menu(self):
        staff_list = database.get_staff_list()
        if not staff_list:
            self.show_error("ไม่พบ Staff กรุณาโหลด Config ใหม่")
            return

        items = [{
            "text": code,
            "viewclass": "OneLineListItem",
            "on_release": lambda code=code: self.select_staff(code),
        } for code in staff_list]

        self.staff_menu = MDDropdownMenu(
            caller=self.ids.btn_staff,
            items=items,
            width_mult=2,
        )
        self.staff_menu.open()

    def select_staff(self, code):
        self.selected_staff = str(code).strip()
        self.ids.btn_staff.text = self.selected_staff or "-เลือก-"

        if self.staff_menu:
            self.staff_menu.dismiss()

        # เปลี่ยน Staff แล้วให้เริ่มรับ Location ใหม่ใน Scan ช่องเดียว
        self.current_location = ""
        self.location_locked = False
        self._set_scan_mode_location()
        self._clear_product_display()
        if "txt_scan" in self.ids:
            self.ids.txt_scan.text = ""
        Clock.schedule_once(lambda _dt: self._focus_scan(), 0.05)

    # =====================================================
    # Single scan flow: Location -> Barcode -> Barcode ...
    # =====================================================
    def change_location(self):
        """กดเปลี่ยน LOC แล้ว Scan ครั้งถัดไปจะถูกใช้เป็น Location ใหม่."""
        self.current_location = ""
        self.location_locked = False
        self._set_scan_mode_location()
        self._clear_product_display()
        if "txt_scan" in self.ids:
            self.ids.txt_scan.text = ""
        Clock.schedule_once(lambda _dt: self._focus_scan(), 0.05)

    def _set_scan_mode_location(self):
        self.scan_guide_text = "กรุณายิง LOCATION"
        self.scan_hint_text = "ยิง LOCATION แล้วกด Enter"

    def _set_scan_mode_barcode(self):
        self.scan_guide_text = "กรุณายิง BARCODE / ITEM CODE"
        self.scan_hint_text = "ยิง BARCODE / ITEM CODE แล้วกด Enter"

    # compatibility with old KV/calls while moving to single scan field
    def toggle_location_lock(self):
        self.change_location()

    def on_scan_input(self):
        widget = self.ids.txt_scan
        value = widget.text.strip()
        if not value:
            return

        # เคลียร์ก่อน process เพื่อลดโอกาส scanner ยิงซ้ำ
        widget.text = ""

        if not self.selected_staff.strip():
            self.show_error("กรุณาเลือก Staff")
            self.open_staff_menu()
            return

        # ยังไม่มี Location -> Scan ครั้งนี้คือ Location
        if not self.current_location.strip() or not self.location_locked:
            self._set_location(value)
            Clock.schedule_once(lambda _dt: self._focus_scan(), 0.05)
            return

        # มี Location แล้ว -> Scan ครั้งนี้คือ Barcode / Item Code
        self.process_barcode(value)
        Clock.schedule_once(lambda _dt: self.force_scan_focus(), 0.20)

    # รองรับชื่อ method เดิมในกรณีมี code อื่นเรียก scan()
    def scan(self):
        self.on_scan_input()

    def _set_location(self, location):
        location = str(location or "").strip()
        if not location:
            return
        self.current_location = location
        self.location_locked = True
        self._set_scan_mode_barcode()

    def process_barcode(self, barcode):
        staff = self.selected_staff.strip()
        location = self.current_location.strip()
        barcode = str(barcode or "").strip()

        if not staff:
            self.show_error("กรุณาเลือก Staff")
            self.open_staff_menu()
            return

        if not location or not self.location_locked:
            self.show_error("กรุณายิง Location ก่อน")
            self.change_location()
            return

        product = database.find_product(barcode)
        if not product:
            self.show_error(f"ไม่พบ Barcode/Item Code [{barcode}]")
            self._clear_product_display()
            return

        try:
            qty, duplicated = database.add_or_increment(
                location,
                staff,
                product["product_code"],
                barcode,
            )
        except Exception as exc:
            self.show_error(f"บันทึกไม่สำเร็จ\n{exc}")
            return

        self.ids.lbl_product_code.text = (
            f"รหัสสินค้า : {product.get('product_code') or '-'}"
        )
        self.ids.lbl_product_name.text = (
            f"ชื่อสินค้า : {product.get('product_name') or '-'}"
        )
        unit = str(product.get("unit") or "").strip()
        suffix = f" {unit}" if unit else ""
        self.ids.lbl_qty.text = f"จำนวนสะสม : {qty}{suffix}"

        play_notification(success=True)
        self.refresh_recent()

    # =====================================================
    # Focus - Scanner TextField เดียว
    # =====================================================
    def _focus_scan(self):
        if "txt_scan" not in self.ids:
            return
        widget = self.ids.txt_scan
        widget.text = ""
        widget.focus = True

    def force_scan_focus(self):
        if "txt_scan" not in self.ids:
            return
        widget = self.ids.txt_scan
        if not widget.focus:
            widget.focus = True

    # compatibility aliases for old internal calls
    def _focus_location(self):
        self._focus_scan()

    def _focus_barcode(self):
        self._focus_scan()

    def force_barcode_focus(self):
        self.force_scan_focus()

    def _clear_product_display(self):
        if "lbl_product_code" in self.ids:
            self.ids.lbl_product_code.text = "รหัสสินค้า : -"
        if "lbl_product_name" in self.ids:
            self.ids.lbl_product_name.text = "ชื่อสินค้า : -"
        if "lbl_qty" in self.ids:
            self.ids.lbl_qty.text = "จำนวนสะสม : -"

    # =====================================================
    # Recent 10 - PENDING only, no header
    # Location ~12 chars | Barcode uses remaining width | Qty ~8 chars
    # =====================================================
    def refresh_recent(self):
        table = self.ids.recent_list
        table.clear_widgets()

        rows = database.recent(10)
        if not rows:
            table.add_widget(MDLabel(
                text="ยังไม่มีรายการ",
                font_name="ThaiFont",
                font_size="11sp",
                halign="left",
                valign="middle",
                size_hint_x=None,
                width=dp(88),
            ))
            table.add_widget(MDLabel(text=""))
            table.add_widget(MDLabel(text="", size_hint_x=None, width=dp(58)))
            return

        for row in rows:
            location = str(row.get("location") or "-")
            scanned_value = str(row.get("scanned_value") or "-")
            qty = str(row.get("qty") or 0)

            cells = (
                RecentClickableLabel(
                    text=location,
                    font_name="ThaiFont",
                    font_size="10sp",
                    halign="left",
                    valign="middle",
                    shorten=True,
                    shorten_from="right",
                    size_hint_x=None,
                    width=dp(88),
                ),
                RecentClickableLabel(
                    text=scanned_value,
                    font_name="ThaiFont",
                    font_size="10sp",
                    halign="left",
                    valign="middle",
                    shorten=True,
                    shorten_from="right",
                    size_hint_x=1,
                ),
                RecentClickableLabel(
                    text=qty,
                    font_name="ThaiFont",
                    font_size="10sp",
                    halign="right",
                    valign="middle",
                    size_hint_x=None,
                    width=dp(58),
                ),
            )

            for cell in cells:
                cell.bind(on_release=partial(self.confirm_delete, row))
                table.add_widget(cell)

    def open_edit_location(self, row, *_):
        field = MDTextField(
            text=str(row.get("location") or ""),
            hint_text="Location ใหม่",
            font_name="ThaiFont",
            multiline=False,
        )
        self._dismiss_dialog()
        self._dialog = MDDialog(
            title="แก้ไข Location",
            type="custom",
            content_cls=field,
            buttons=[
                MDFlatButton(
                    text="ยกเลิก", font_name="ThaiFont",
                    on_release=lambda *_: self._dismiss_dialog(),
                ),
                MDRaisedButton(
                    text="บันทึก", font_name="ThaiFont",
                    on_release=lambda *_: self._save_location(row["id"], field.text),
                ),
            ],
        )
        self._dialog.open()
        Clock.schedule_once(lambda _dt: setattr(field, "focus", True), .15)

    def _save_location(self, row_id, new_location):
        try:
            database.update_pending_location(row_id, new_location)
            self._dismiss_dialog()
            self.refresh_recent()
            self._focus_scan()
        except Exception as exc:
            self.show_error(str(exc))

    def confirm_delete(self, row, *_):
        self._dismiss_dialog()
        self._dialog = MDDialog(
            title="ยืนยันการลบ",
            text=(
                f"Location: {row.get('location', '-')}\n"
                f"สินค้า: {row.get('product_code', '-')}\n"
                f"จำนวน: {row.get('qty', 0)}"
            ),
            buttons=[
                MDFlatButton(
                    text="ยกเลิก", font_name="ThaiFont",
                    on_release=lambda *_: self._dismiss_dialog(),
                ),
                MDRaisedButton(
                    text="ลบ", font_name="ThaiFont",
                    on_release=lambda *_: self._delete_row(row["id"]),
                ),
            ],
        )
        self._dialog.open()

    def _delete_row(self, row_id):
        try:
            database.delete_pending_row(row_id)
            self._dismiss_dialog()
            self.refresh_recent()
            Clock.schedule_once(lambda _dt: self._focus_scan(), 0.05)
        except Exception as exc:
            self.show_error(str(exc))

    def _dismiss_dialog(self):
        if self._dialog is not None:
            try:
                self._dialog.dismiss()
            except Exception:
                pass
            self._dialog = None

class CountStockExportScreen(CountStockBaseScreen):
    exporting = False

    TARGETS = (
        ("Countstock_scan_data", "scan_data"),
        ("Countstock_scan_slottag", "scan_slottag"),
    )

    def on_enter(self, *args):
        self.refresh_stats()

    def go_back(self):
        self.manager.current = "countstock_menu"

    def refresh_stats(self):
        stats = database.get_scan_stats()
        self.ids.lbl_export_count.text = (
            f"ข้อมูลทั้งหมด {stats['total_count']:,} รายการ\n"
            f"Sync แล้ว {stats['synced_count']:,} | "
            f"ยังไม่ Sync {stats['pending_count']:,}\n"
            f"scan_data {stats['scan_data_count']:,} | "
            f"scan_slottag {stats['slottag_count']:,}"
        )
        # ปุ่มทั้งสองใช้ได้เมื่อมีข้อมูลชุดใหม่ที่ยังไม่ Export ไปปลายทางใดเลย
        disabled = self.exporting or stats["pending_count"] <= 0
        self.ids.btn_export_scan_data.disabled = disabled
        self.ids.btn_export_slottag.disabled = disabled

    def export_to(self, table_name):
        if self.exporting:
            return
        target = next((x for x in self.TARGETS if x[0] == table_name), None)
        if not target:
            self.show_error("ตาราง Export ไม่ถูกต้อง")
            return
        rows = database.export_rows(table_name)
        if not rows:
            self.show_error("ไม่มีข้อมูลชุดใหม่สำหรับ Export")
            self.refresh_stats()
            return

        # ล็อกทั้งสองปุ่มทันที: ข้อมูลชุดนี้เลือก Export ได้เพียงอย่างเดียว
        self.exporting = True
        self.refresh_stats()
        display_name = target[1]
        self.ids.lbl_status.text = (
            f"กำลัง Sync {display_name} {len(rows):,} รายการ..."
        )
        jobs = [(table_name, display_name, rows)]
        threading.Thread(target=self._worker, args=(jobs,), daemon=True).start()

    def _worker(self, jobs):
        completed = []
        try:
            config = database.get_config()
            if not config:
                raise ValueError("กรุณาตั้งค่า CountStock ก่อน")
            url = f"http://{config['iis_server_ip']}{API_ROOT}/Export.ashx"

            for table_name, display_name, rows in jobs:
                payload = {
                    "table": table_name,
                    "db_server_ip": config.get("db_server_ip", ""),
                    "db_name": config.get("db_name", ""),
                    "data": [{
                        "location": r["location"],
                        "staff": r["staff_name"],
                        "p_code": r["product_code"],
                        "barcode": r["barcode"],
                        "qty": r["qty"],
                        "date": r["scan_date"],
                    } for r in rows],
                }
                response = requests.post(url, json=payload, timeout=300)
                if response.status_code >= 400:
                    try:
                        error_message = response.json().get("message") or response.text
                    except Exception:
                        error_message = response.text
                    raise RuntimeError(
                        f"{display_name}: Export Error {response.status_code}: {error_message}"
                    )
                result = response.json()
                if not bool(result.get("success", False)):
                    raise RuntimeError(
                        f"{display_name}: "
                        f"{result.get('message') or 'Server ปฏิเสธการส่งข้อมูล'}"
                    )
                synced_count = database.mark_rows_synced(
                    [row["id"] for row in rows], table_name
                )
                completed.append((display_name, synced_count))

            Clock.schedule_once(
                lambda _dt, done=list(completed): self._done(done), 0
            )
        except Exception as exc:
            Clock.schedule_once(
                lambda _dt, e=str(exc), done=list(completed): self._failed(e, done), 0
            )

    def _done(self, completed):
        self.exporting = False
        detail = " | ".join(f"{name} {count:,}" for name, count in completed)
        self.ids.lbl_status.text = f"Sync สำเร็จ: {detail}"
        self.refresh_stats()
        self.show_success(f"ส่งออกสำเร็จ\n{detail}")

    def _failed(self, message, completed=None):
        self.exporting = False
        completed = completed or []
        if completed:
            detail = " | ".join(f"{name} {count:,}" for name, count in completed)
            self.ids.lbl_status.text = f"สำเร็จบางส่วน: {detail}"
            message = f"สำเร็จแล้ว: {detail}\nรายการถัดไปผิดพลาด: {message}"
        else:
            self.ids.lbl_status.text = "ส่งออกไม่สำเร็จ"
        self.refresh_stats()
        self.show_error(message)

    def clear_data(self):
        database.clear_scans()
        self.ids.lbl_status.text = "ล้างข้อมูลแล้ว"
        self.refresh_stats()
        self.show_success("ล้างรายการ CountStock ในเครื่องแล้ว")