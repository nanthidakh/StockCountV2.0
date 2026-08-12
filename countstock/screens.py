from __future__ import annotations

import threading
import requests
from functools import partial
from kivy.app import App
from kivy.utils import platform
from kivy.clock import Clock
from kivy.factory import Factory
from kivy.properties import BooleanProperty
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from screens.base_screen import BaseScreen, ScannerTextField
from countstock import database
from countstock.sound import play_notification

API_ROOT = "/API_HWK_CountStock_Data"


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
    location_locked = BooleanProperty(False)
    _dialog = None

    staff_menu = None
    selected_staff = ""

    def on_enter(self, *args):
        self._load_staff_dropdown()
        self.refresh_recent()
        self._update_location_lock_ui()
        Clock.schedule_once(lambda _dt: self._focus_barcode(), .2)

    def go_back(self):
        self._dismiss_dialog()
        self.manager.current = "countstock_menu"

    def prepare_field(self, widget, touch, clear_value=True):
        """แตะช่องแล้วเตรียมรับค่าจาก Scanner โดยไม่สลับ Focus ไปมา."""
        if not widget.collide_point(*touch.pos):
            return False
        if getattr(touch, "is_mouse_scrolling", False):
            return False

        if clear_value:
            widget.text = ""
        self._keep_focus(widget)
        return False

    def prepare_location_field(self, widget, touch):
        if not widget.collide_point(*touch.pos):
            return False
        if getattr(touch, "is_mouse_scrolling", False):
            return False

        if self.location_locked:
            self.ids.lbl_result.text = "Location ถูกล็อก กด 'ปลดล็อก LOC' ก่อนเปลี่ยน"
            self._focus_barcode()
            return True

        widget.text = ""
        self._keep_focus(widget)
        return False

    def _keep_focus(self, widget):
        """คืน Focus หลัง UI update โดยไม่ toggle focus และไม่เปิด Soft Keyboard."""
        def _apply_focus(_dt):
            try:
                if not widget.focus:
                    widget.focus = True
                self._hide_android_keyboard()
            except Exception:
                pass

        # รอ event จาก Enter / refresh_recent จบก่อน เพื่อไม่ให้ focus ถูก widget อื่นแย่ง
        Clock.schedule_once(_apply_focus, 0.08)

    @staticmethod
    def _hide_android_keyboard():
        if platform != "android":
            return
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            activity = PythonActivity.mActivity
            imm = activity.getSystemService(Context.INPUT_METHOD_SERVICE)
            view = activity.getWindow().getDecorView()
            imm.hideSoftInputFromWindow(view.getWindowToken(), 0)
        except Exception:
            # การซ่อน keyboard ต้องไม่ทำให้หน้าสแกนหยุดทำงาน
            pass

    def toggle_location_lock(self):
        location = self.ids.txt_location.text.strip()
        if self.location_locked:
            self.location_locked = False
            self.ids.txt_location.text = ""
            self.ids.lbl_result.text = "ปลดล็อก Location แล้ว กรุณายิง Location ใหม่"
            self._update_location_lock_ui()
            self._focus_location(clear_value=False)
            return
        if not location:
            self.show_error("กรุณากรอก Location ก่อนล็อก")
            self._focus_location(clear_value=False)
            return
        self.location_locked = True
        self.ids.lbl_result.text = f"ล็อก Location: {location}"
        self._update_location_lock_ui()
        self._focus_barcode()

    def _update_location_lock_ui(self):
        if "btn_lock_location" in self.ids:
            self.ids.btn_lock_location.text = (
                "ปลดล็อก LOC" if self.location_locked else "ล็อก LOC"
            )
        if "txt_location" in self.ids:
            self.ids.txt_location.readonly = self.location_locked

    def _load_staff_dropdown(self):
        staff_list = database.get_staff_list()
        if self.selected_staff not in staff_list:
            self.selected_staff = ""
        if "btn_staff" in self.ids:
            self.ids.btn_staff.text = self.selected_staff or "เลือก Staff"

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
            caller=self.ids.btn_staff, items=items, width_mult=2
        )
        self.staff_menu.open()

    def select_staff(self, code):
        self.selected_staff = str(code)
        self.ids.btn_staff.text = self.selected_staff
        if self.staff_menu:
            self.staff_menu.dismiss()
        if self.location_locked:
            self._focus_barcode()
        else:
            self._focus_location(clear_value=False)

    def on_location_validate(self):
        if not self.ids.txt_location.text.strip():
            self.show_error("กรุณากรอก Location")
            self._focus_location(clear_value=False)
            return
        self.location_locked = True
        self._update_location_lock_ui()
        self._focus_barcode()

    def scan(self):
        value = self.ids.txt_barcode.text.strip()
        if not value:
            self._focus_barcode()
            return

        self.ids.txt_barcode.text = ""
        staff = self.selected_staff.strip()
        location = self.ids.txt_location.text.strip()

        if not staff:
            self.show_error("กรุณาเลือก Staff")
            self.open_staff_menu()
            return
        if not location:
            self.location_locked = False
            self._update_location_lock_ui()
            self.show_error("กรุณากรอก Location")
            self._focus_location(clear_value=True)
            return
        if not self.location_locked:
            self.location_locked = True
            self._update_location_lock_ui()

        product = database.find_product(value)
        if not product:
            self.ids.lbl_result.text = f"ไม่พบสินค้า: {value}"
            self.show_error(f"ไม่พบ Barcode/Item Code [{value}]")
            self._focus_barcode()
            return

        qty, duplicated = database.add_or_increment(
            location, staff, product["product_code"], value
        )
        prefix = "ยิงซ้ำ +1" if duplicated else "บันทึกแล้ว"
        self.ids.lbl_result.text = (
            f"{prefix}: {product['product_code']}\n"
            f"{product['product_name']} | จำนวน {qty} {product.get('unit', '')}"
        )
        play_notification(success=True)
        self.refresh_recent()
        self._focus_barcode()

    def _focus_staff(self, clear_value=False):
        # Staff ใช้ Dropdown แล้ว ไม่รับการพิมพ์จาก Scanner
        if clear_value:
            self.selected_staff = ""
            if "btn_staff" in self.ids:
                self.ids.btn_staff.text = "เลือก Staff"

    def _focus_location(self, clear_value=False):
        if self.location_locked:
            self._focus_barcode()
            return
        widget = self.ids.txt_location
        if clear_value:
            widget.text = ""
        self._keep_focus(widget)

    def _focus_barcode(self):
        widget = self.ids.txt_barcode
        widget.text = ""
        self._keep_focus(widget)

    def refresh_recent(self):
        self.ids.recent_list.clear_widgets()
        rows = database.recent(10)
        if not rows:
            self.ids.recent_list.add_widget(MDLabel(
                text="ยังไม่มีรายการ",
                font_name="ThaiFont",
                halign="center",
                size_hint_y=None,
                height="44dp",
            ))
            return

        for row in rows:
            locked = database.row_has_been_synced(row)
            product_name = str(row.get("product_name") or "-")[:100]
            box = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height="52dp",
                spacing="2dp",
                padding=("2dp", "1dp"),
            )
            detail = MDLabel(
                text=(
                    f"{row.get('location', '-')} | "
                    f"{row.get('product_code', '-')}:"
                    f"{product_name} Qty : {row.get('qty', 0)}\n"
                ),
                font_name="ThaiFont",
                font_size="9sp",
                halign="left",
                valign="middle",
                text_size=(self.width, None),
                shorten=True,
                shorten_from="right",
            )
            box.add_widget(detail)

            edit_button = MDFlatButton(
                text="แก้ LOC",
                font_name="ThaiFont",
                font_size="13sp",
                size_hint_x=None,
                width="56dp",
                disabled=locked,
            )
            edit_button.bind(on_release=partial(self.open_edit_location, dict(row)))
            box.add_widget(edit_button)

            delete_button = MDFlatButton(
                text="ลบ",
                font_name="ThaiFont",
                font_size="13sp",
                size_hint_x=None,
                width="36dp",
                disabled=locked,
            )
            delete_button.bind(on_release=partial(self.confirm_delete, dict(row)))
            box.add_widget(delete_button)
            self.ids.recent_list.add_widget(box)

    def open_edit_location(self, row, *_):
        if database.row_has_been_synced(row):
            self.show_error("รายการที่ Sync แล้วไม่สามารถแก้ Location ได้")
            return
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
            self.ids.lbl_result.text = f"แก้ Location เป็น {str(new_location).strip()} แล้ว"
            self._focus_barcode()
        except Exception as exc:
            self.show_error(str(exc))

    def confirm_delete(self, row, *_):
        if database.row_has_been_synced(row):
            self.show_error("รายการที่ Sync แล้วไม่สามารถลบได้")
            return
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
            self.ids.lbl_result.text = "ลบรายการแล้ว"
            self._focus_barcode()
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