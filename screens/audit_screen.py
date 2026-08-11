"""Audit Screen: Offline, Recent/Correction and shared Sync."""
import threading
from functools import partial

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.button import Button
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.screen import MDScreen

from services.audit_service import AuditService
from services.sync_service import SyncService


class AuditScreen(MDScreen):
    current_plan = None
    current_location = None
    current_item = None
    current_detail = None
    pending_duplicate = None
    duplicate_mode = None
    selected_recent_rows = None
    correction_mode = "QTY"
    _dialog = None
    _busy = False
    _sync_status_in_flight = False
    _local_sync_summary = None
    _server_sync_summary = None
    is_changing_location = False
    _previous_location = None
    _verify_location_active = False
    _verify_location_count = 0
    _verify_expect = "LOCATION"
    _verify_scanned_location = None
    _verify_item = None
    _verify_barcode = None

    def on_enter(self, *args):
        self.selected_recent_rows = {}
        self.current_location = None
        self.is_changing_location = False
        self._previous_location = None
        self.current_item = None
        self.current_detail = None
        self._local_sync_summary = {"PENDING": 0, "SYNCING": 0, "SYNCED": 0, "ERROR": 0}
        self._server_sync_summary = {"WAITING": 0, "PROCESSING": 0, "SUCCESS": 0, "ERROR": 0, "LOADED": False}
        self.ids.audit_tab_manager.current = "audit_tab"
        self._set_tab("audit_tab")
        self._load_device()
        self.load_plan()

    def _load_device(self):
        app = App.get_running_app()
        name = str(getattr(app, "device_name", "") or "UNKNOWN_DEVICE")
        app.device_name = name
        self.ids.txt_checker.text = f"Auditor: {name}"

    def load_plan(self):
        try:
            result = AuditService(App.get_running_app().db).get_current_plan()
            if result["status"] != "READY":
                self.current_plan = None
                self.ids.lbl_plan_name.text = "ยังไม่มีใบงาน"
                self.ids.lbl_status.text = result.get("message", "ไม่พบใบงาน")
                self._enable_audit(False)
                return
            self.current_plan = result["plan"]
            app = App.get_running_app()
            app.plan_id = int(self.current_plan["plan_id"])
            code = self.current_plan.get("plan_code") or self.current_plan.get("plan_details") or self.current_plan["plan_id"]
            self.ids.lbl_plan_name.text = f"แผนตรวจนับ: {code}"
            self.ids.lbl_status.text = "กรุณายิง Location"
            self._enable_audit(True)
            self.reset_location()
            self.load_recent()
        except Exception as exc:
            self.ids.lbl_status.text = f"อ่านใบงานไม่สำเร็จ: {exc}"
            self._enable_audit(False)

    def _enable_audit(self, enabled):
        self.ids.txt_barcode.disabled = not enabled
        self.ids.txt_qty.disabled = True
        self.ids.btn_save.disabled = True
        self.ids.btn_change_location.disabled = (not enabled) or (self.current_location is None)
        self.ids.btn_calculator.disabled = not enabled

    def process_scan(self, scan_value):
        scan_value = str(scan_value or "").strip()
        self.ids.txt_barcode.text = ""
        if not scan_value or not self.current_plan:
            self._focus_scan(); return
        if self._verify_location_active:
            self._verify_location_scan(scan_value)
        elif self.is_changing_location or self.current_location is None:
            self.scan_location(scan_value)
        else:
            self.scan_item(scan_value)

    def scan_location(self, scan_value):
        changing_location = bool(self.is_changing_location)
        result = AuditService(App.get_running_app().db).scan_location(
            self.current_plan["plan_id"], scan_value
        )
        if result["status"] != "SUCCESS":
            self.ids.lbl_status.text = "ไม่พบ Location ในใบงาน"
            self._focus_scan()
            return

        self.current_location = result["location"]
        code = self.current_location.get("location_code") or self.current_location.get("location_id")
        self.ids.lbl_location.text = str(code)
        self.is_changing_location = False
        self._previous_location = None
        self.ids.btn_change_location.text = "เปลี่ยน"
        self.ids.btn_change_location.disabled = False
        self._set_scan_prompt("ITEM")
        self.ids.lbl_status.text = (
            "เปลี่ยน Location สำเร็จ กรุณายิง Barcode สินค้า"
            if changing_location
            else "กรุณายิง Barcode สินค้า หรือกรอกรหัสสินค้า"
        )
        self._clear_item()
        self._focus_scan()

    def scan_item(self, scan_value):
        result = AuditService(App.get_running_app().db).prepare_item(
            self.current_plan["plan_id"], self.current_location["location_id"], scan_value,
        )
        status = result["status"]
        if status == "WRONG_LOCATION":
            self._start_location_verification(result.get("item"), scan_value); return
        if status != "READY":
            self.ids.lbl_status.text = "สินค้าไม่อยู่ในใบงาน Audit" if status == "UNEXPECTED_ITEM" else "ไม่พบสินค้า"
            self._focus_scan(); return
        self.current_item = result["item"]
        self.current_detail = result["detail"]
        self.current_item["scanned_barcode"] = scan_value
        self.ids.lbl_item_code.text = f"รหัส: {self.current_item.get('item_code','-')}"
        self.ids.lbl_item_name.text = f"ชื่อ: {self.current_item.get('item_name','-')}"
        self.ids.lbl_unit.text = f"หน่วย: {self.current_item.get('uom') or self.current_item.get('unit_name') or '-'}"
        self.ids.txt_qty.text = ""
        self.pending_duplicate = result.get("duplicate")
        self.duplicate_mode = None

        # รายการซ้ำต้องให้ผู้ใช้เลือกวิธีทำงานก่อนเปิดช่องกรอก Qty
        if self.pending_duplicate:
            self.ids.txt_qty.disabled = True
            self.ids.btn_save.disabled = True
            self.ids.lbl_status.text = "พบ Audit รายการเดิม กรุณาเลือกวิธีบันทึก"
            self._show_duplicate(self.pending_duplicate)
            return

        self.ids.txt_qty.disabled = False
        self.ids.btn_save.disabled = False
        self.ids.lbl_status.text = "กรอก Qty Audit แล้วบันทึก"
        Clock.schedule_once(lambda dt: setattr(self.ids.txt_qty, "focus", True), .1)

    def _start_location_verification(self, item, barcode):
        # 1 รอบยืนยัน = Location ก่อน แล้วสินค้า
        self._verify_location_active = True
        self._verify_location_count = 0
        self._verify_expect = "LOCATION"
        self._verify_scanned_location = None
        self._verify_item = item
        self._verify_barcode = barcode
        self._clear_item()
        self.ids.txt_qty.disabled = True
        self.ids.btn_save.disabled = True
        self.ids.txt_barcode.hint_text = "ยิง Location ยืนยัน (1/3)"
        self.ids.lbl_status.text = (
            "สินค้าไม่อยู่ Location นี้ กรุณายิง Location เดิมก่อน (1/3)"
        )
        self._focus_scan()

    def _verify_location_scan(self, scan_value):
        """Verify Location -> Item 3 rounds; a valid Plan pair exits to normal flow immediately."""
        service = AuditService(App.get_running_app().db)
        plan_id = self.current_plan["plan_id"]
        round_no = self._verify_location_count + 1

        if self._verify_expect == "LOCATION":
            result = service.scan_location(plan_id, scan_value)
            loc = result.get("location") if result.get("status") == "SUCCESS" else None
            if not loc:
                self._verify_location_count = 0
                self._verify_scanned_location = None
                self.ids.txt_barcode.hint_text = "ยิง Location ยืนยัน (1/3)"
                self.ids.lbl_status.text = "ไม่พบ Location ใน Plan เริ่มยืนยันใหม่ (1/3)"
                self._focus_scan()
                return

            self._verify_scanned_location = loc
            self._verify_expect = "ITEM"
            self.ids.txt_barcode.hint_text = f"ยิง Barcode สินค้า ({round_no}/3)"
            self.ids.lbl_status.text = f"พบ Location ใน Plan ({round_no}/3) กรุณายิง Barcode สินค้า"
            self._focus_scan()
            return

        loc = self._verify_scanned_location
        location_id = int((loc or {}).get("location_id") or 0)
        result = service.prepare_item(plan_id, location_id, scan_value)

        # ถ้าคู่ Location + Item มีอยู่ใน Plan จริง กลับเข้า Audit flow ปกติทันที
        if isinstance(result, dict) and result.get("status") == "READY":
            self._verify_location_active = False
            self._verify_location_count = 0
            self._verify_expect = "LOCATION"
            self._verify_scanned_location = None
            self._verify_item = None
            self._verify_barcode = None
            self.current_location = loc
            self.ids.lbl_location.text = str(loc.get("location_code") or loc.get("location_id") or "-")
            self.ids.btn_change_location.text = "เปลี่ยน"
            self.ids.btn_change_location.disabled = False
            self._set_scan_prompt("ITEM")
            self.scan_item(scan_value)
            return

        scanned_item = result.get("item") if isinstance(result, dict) else None
        expected_code = str((self._verify_item or {}).get("item_code") or "").strip()
        scanned_code = str((scanned_item or {}).get("item_code") or "").strip()
        current_location_id = int((self.current_location or {}).get("location_id") or 0)

        if location_id != current_location_id or not scanned_item or not expected_code or scanned_code != expected_code:
            self._verify_location_count = 0
            self._verify_expect = "LOCATION"
            self._verify_scanned_location = None
            self.ids.txt_barcode.hint_text = "ยิง Location ยืนยัน (1/3)"
            self.ids.lbl_status.text = "คู่ Location + สินค้าไม่ตรง เริ่มใหม่ กรุณายิง Location (1/3)"
            self._focus_scan()
            return

        self._verify_barcode = scan_value
        self._verify_location_count += 1
        self._verify_scanned_location = None

        if self._verify_location_count >= 3:
            self._verify_expect = "LOCATION"
            self._show_add_location_dialog()
            return

        next_round = self._verify_location_count + 1
        self._verify_expect = "LOCATION"
        self.ids.txt_barcode.hint_text = f"ยิง Location ยืนยัน ({next_round}/3)"
        self.ids.lbl_status.text = (
            f"ยืนยันคู่ Location + สินค้าแล้ว {self._verify_location_count}/3 "
            f"กรุณายิง Location รอบ {next_round}/3"
        )
        self._focus_scan()

    def _show_add_location_dialog(self):
        self._dismiss_dialog(); self.ids.txt_barcode.disabled=True
        self._dialog=MDDialog(
            title="ยืนยันเพิ่มสินค้าใน Location นี้",
            text=f"สินค้า: {self._verify_item.get('item_code','-')}\nLocation: {self.current_location.get('location_code','-')}\nยืนยัน Location ครบ 3/3 ครั้ง",
            buttons=[
                MDFlatButton(text="ยกเลิก",font_name="ThaiFont",on_release=lambda *_:self._cancel_location_verification()),
                MDRaisedButton(text="เพิ่ม Location นี้",font_name="ThaiFont",on_release=lambda *_:self._confirm_new_plan_detail()),
            ])
        self._dialog.open()

    def _cancel_location_verification(self):
        self._dismiss_dialog(); self._verify_location_active=False; self._verify_location_count=0; self._verify_expect="LOCATION"; self._verify_scanned_location=None
        self._verify_item=None; self._verify_barcode=None; self.ids.txt_barcode.disabled=False
        self._set_scan_prompt("ITEM"); self.ids.lbl_status.text="ยกเลิกการเพิ่ม Location กรุณายิง Barcode สินค้า"; self._focus_scan()

    def _confirm_new_plan_detail(self):
        try:
            service=AuditService(App.get_running_app().db)
            detail=service.create_local_plan_detail(self.current_plan["plan_id"],self._verify_item["item_id"],self.current_location["location_id"])
            if not detail: raise ValueError("สร้าง Local Plan Detail ไม่สำเร็จ")
            self._dismiss_dialog(); self.current_item=self._verify_item; self.current_detail=detail
            self.current_item["scanned_barcode"]=self._verify_barcode
            self._verify_location_active=False; self._verify_location_count=0; self._verify_expect="LOCATION"; self._verify_item=None; self._verify_barcode=None
            self.ids.txt_barcode.disabled=False
            self.ids.lbl_item_code.text=f"รหัส: {self.current_item.get('item_code','-')}"
            self.ids.lbl_item_name.text=f"ชื่อ: {self.current_item.get('item_name','-')}"
            self.ids.lbl_unit.text=f"หน่วย: {self.current_item.get('uom') or '-'}"
            self.ids.txt_qty.text=""; self.ids.txt_qty.disabled=False; self.ids.btn_save.disabled=False
            self.ids.lbl_status.text="เพิ่ม Location แล้ว กรุณากรอก Qty Audit และบันทึก"
            Clock.schedule_once(lambda dt:setattr(self.ids.txt_qty,"focus",True),.1)
        except Exception as exc:
            self.ids.lbl_status.text=f"เพิ่ม Location ไม่สำเร็จ: {exc}"; self.ids.txt_barcode.disabled=False; self._cancel_location_verification()

    def save_current(self, duplicate_mode=None):
        if not self.current_item or not self.current_detail:
            return
        try:
            qty = float(str(self.ids.txt_qty.text or "").strip())
            if qty < 0: raise ValueError
        except ValueError:
            self.ids.lbl_status.text = "Qty Audit ไม่ถูกต้อง"
            return
        # รายการซ้ำต้องผ่านการเลือก เพิ่ม/แทนที่ จาก Popup ก่อนกรอก Qty
        if self.pending_duplicate and not (duplicate_mode or self.duplicate_mode):
            self._show_duplicate(self.pending_duplicate)
            return

        mode = duplicate_mode or self.duplicate_mode or "ADD"
        try:
            result = AuditService(App.get_running_app().db).save_audit(
                self.current_detail, self.current_item, self.current_location["location_id"],
                self.current_item.get("scanned_barcode", ""), qty,
                App.get_running_app().device_name, mode,
            )
            if result.get("cancelled"):
                self.ids.lbl_status.text = "ยกเลิกการบันทึก"
                return
            self.ids.lbl_status.text = f"บันทึก Audit สำเร็จ Qty {self._fmt(result['qty_audit'])}"
            self._clear_item(); self.load_recent(); self.refresh_sync(); self._focus_scan()
        except Exception as exc:
            self.ids.lbl_status.text = f"บันทึกไม่สำเร็จ: {exc}"

    def _show_duplicate(self, row):
        """แสดงข้อมูลเดิมแบบกระชับ ก่อนให้ผู้ใช้กรอก Qty ใหม่"""
        self._dismiss_dialog()

        server_audit = self.current_detail.get("server_qty_audit", 0)

        text = (
            f"Stock คงเหลือ : {self._fmt(self.current_detail.get('qty'))}\n"
            f"On Hand       : {self._fmt(self.current_detail.get('qty_on_hand'))}\n"
            f"Audit เดิม    : {self._fmt(server_audit)}\n"
            f"Audit ปัจจุบัน: {self._fmt(row.get('qty'))}"
        )

        self._dialog = MDDialog(
            title="Audit ซ้ำ Location เดิม",
            text=text,
            buttons=[
                MDFlatButton(
                    text="ยกเลิก",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._cancel_duplicate(),
                ),
                MDFlatButton(
                    text="แทนที่",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._choose_duplicate("REPLACE"),
                ),
                MDRaisedButton(
                    text="เพิ่ม",
                    font_name="ThaiFont",
                    on_release=lambda *_: self._choose_duplicate("ADD"),
                ),
            ],
        )
        self._dialog.open()

    def _choose_duplicate(self, mode):
        """จำวิธีบันทึก แล้วจึงเปิดให้กรอก Qty"""
        self.duplicate_mode = str(mode or "").upper()
        self._dismiss_dialog()

        self.ids.txt_qty.text = ""
        self.ids.txt_qty.disabled = False
        self.ids.btn_save.disabled = False

        if self.duplicate_mode == "REPLACE":
            self.ids.lbl_status.text = "กรอก Qty ใหม่เพื่อแทนที่ Audit ปัจจุบัน"
        else:
            self.ids.lbl_status.text = "กรอก Qty ที่ต้องการบวกเพิ่ม"

        Clock.schedule_once(
            lambda dt: setattr(self.ids.txt_qty, "focus", True),
            0.1,
        )

    def _save_duplicate(self, mode):
        # รองรับชื่อ Method เดิม หากมีจุดเรียกจาก KV/Code รุ่นก่อน
        self._choose_duplicate(mode)

    def _cancel_duplicate(self):
        self._dismiss_dialog()
        self._clear_item()
        self.ids.lbl_status.text = "ยกเลิกรายการซ้ำ"
        self._focus_scan()

    def _set_scan_prompt(self, mode):
        mode = str(mode or "").upper()
        if mode == "ITEM":
            self.ids.txt_barcode.hint_text = "ยิง Barcode สินค้า / กรอกรหัสสินค้า"
        elif mode == "CHANGE_LOCATION":
            self.ids.txt_barcode.hint_text = "ยิง Location ใหม่"
        else:
            self.ids.txt_barcode.hint_text = "ยิง Location"

    def toggle_change_location(self):
        if self._verify_location_active:
            self._cancel_location_verification()
            return

        if self.is_changing_location:
            self.is_changing_location = False
            self.current_location = self._previous_location
            self._previous_location = None
            self.ids.btn_change_location.text = "เปลี่ยน"
            self._set_scan_prompt("ITEM" if self.current_location else "LOCATION")
            self.ids.lbl_status.text = (
                "ยกเลิกการเปลี่ยน Location กรุณายิง Barcode สินค้า"
                if self.current_location
                else "กรุณายิง Location"
            )
            self._focus_scan()
            return

        if self.current_location is None:
            self.ids.lbl_status.text = "กรุณายิง Location ก่อน"
            self._set_scan_prompt("LOCATION")
            self._focus_scan()
            return

        self._previous_location = self.current_location
        self.is_changing_location = True
        self._clear_item()
        self.ids.btn_change_location.text = "ยกเลิก"
        self._set_scan_prompt("CHANGE_LOCATION")
        self.ids.lbl_status.text = "กรุณายิง Location ใหม่"
        self._focus_scan()

    def reset_location(self):
        self.current_location = None
        self.is_changing_location = False
        self._previous_location = None
        self.ids.lbl_location.text = "กรุณายิง Barcode Location"
        self.ids.btn_change_location.text = "เปลี่ยน"
        self.ids.btn_change_location.disabled = True
        self._set_scan_prompt("LOCATION")
        self._clear_item()
        self._focus_scan()

    def _clear_item(self):
        self.current_item = None; self.current_detail = None
        self.pending_duplicate = None; self.duplicate_mode = None
        self.ids.lbl_item_code.text = "รหัส: -"; self.ids.lbl_item_name.text = "ชื่อ: -"
        self.ids.lbl_unit.text = "หน่วย: -"
        self.ids.txt_qty.text = ""; self.ids.txt_qty.disabled = True; self.ids.btn_save.disabled = True

    def switch_tab(self, name):
        self.ids.audit_tab_manager.current = name; self._set_tab(name)
        if name == "recent_tab": self.load_recent()
        elif name == "sync_tab": self.refresh_sync()

    def _set_tab(self, name):
        self.ids.tab_audit.disabled = name == "audit_tab"
        self.ids.tab_recent.disabled = name == "recent_tab"
        self.ids.tab_sync.disabled = name == "sync_tab"

    def load_recent(self):
        if not self.current_plan: return
        box = self.ids.recent_list; box.clear_widgets()
        rows = AuditService(App.get_running_app().db).get_recent(self.current_plan["plan_id"], 15)
        for row in rows:
            selected = int(row["history_id"]) in self.selected_recent_rows
            prefix = "[✓] " if selected else ""
            button = Button(
                text=f"{prefix}{row.get('location_code','-')} | {row.get('item_code','-')} | {self._fmt(row.get('qty'))} {row.get('uom','')}",
                size_hint_y=None, height="46dp", font_name="ThaiFont",
            )
            button.bind(on_release=partial(self._select_recent, dict(row)))
            box.add_widget(button)

    def set_correction_mode(self, mode):
        self.correction_mode = mode
        self.selected_recent_rows = {}
        self.ids.lbl_recent_mode.text = "แก้ Qty: เลือก 1 รายการ" if mode == "QTY" else "แก้ Location: เลือกหลายรายการ"
        self.ids.btn_apply_location.disabled = mode != "LOCATION"
        self.load_recent()

    def _select_recent(self, row, *_):
        hid = int(row["history_id"])
        queue_status = str(row.get("queue_status") or "PENDING").upper()
        if queue_status not in ("PENDING", "ERROR"):
            self.ids.lbl_status.text = "รายการนี้กำลัง Sync หรือ Sync แล้ว ไม่สามารถแก้ไขได้"
            return
        if self.correction_mode == "QTY":
            self.selected_recent_rows = {hid: row}; self._qty_dialog(row)
        else:
            if hid in self.selected_recent_rows: self.selected_recent_rows.pop(hid)
            else: self.selected_recent_rows[hid] = row
            self.ids.btn_apply_location.text = f"แก้ LOC ({len(self.selected_recent_rows)})"
            self.load_recent()

    def _qty_dialog(self, row):
        from kivymd.uix.textfield import MDTextField
        field = MDTextField(
            hint_text="Qty Audit ใหม่",
            input_filter="float",
            multiline=False,
            font_name="ThaiFont",
        )
        self._dismiss_dialog()
        self._dialog = MDDialog(
            title=f"แก้ Qty {row.get('item_code','')}", type="custom", content_cls=field,
            buttons=[MDFlatButton(text="ยกเลิก",font_name="ThaiFont",on_release=lambda *_:self._dismiss_dialog()),
                     MDRaisedButton(text="บันทึก",font_name="ThaiFont",on_release=lambda *_:self._apply_qty(row,field.text))]
        ); self._dialog.open()

    def _apply_qty(self, row, text):
        try:
            AuditService(App.get_running_app().db).correct_qty(row["history_id"], text, App.get_running_app().device_name)
            self._dismiss_dialog(); self.ids.lbl_status.text="แก้ Qty Audit แล้ว"; self.load_recent(); self.refresh_sync()
        except Exception as exc: self.ids.lbl_status.text=f"แก้ Qty ไม่สำเร็จ: {exc}"

    def apply_location_correction(self):
        if not self.selected_recent_rows: return
        from kivymd.uix.textfield import MDTextField
        field=MDTextField(
            hint_text="ยิง/กรอก Location ใหม่",
            multiline=False,
            font_name="ThaiFont",
        )
        self._dismiss_dialog(); self._dialog=MDDialog(
            title=f"แก้ Location {len(self.selected_recent_rows)} รายการ",type="custom",content_cls=field,
            buttons=[MDFlatButton(text="ยกเลิก",font_name="ThaiFont",on_release=lambda *_:self._dismiss_dialog()),
                     MDRaisedButton(text="บันทึก",font_name="ThaiFont",on_release=lambda *_:self._apply_location(field.text))]
        ); self._dialog.open()

    def _apply_location(self, code):
        try:
            result=AuditService(App.get_running_app().db).correct_locations(
                list(self.selected_recent_rows),code,self.current_plan["plan_id"],App.get_running_app().device_name)
            self._dismiss_dialog(); self.selected_recent_rows={}; self.ids.lbl_status.text=f"แก้ Location {result['updated']} รายการแล้ว"; self.load_recent(); self.refresh_sync()
        except Exception as exc: self.ids.lbl_status.text=f"แก้ Location ไม่สำเร็จ: {exc}"

    def refresh_sync(self):
        # GetSyncStatus runs only when the Sync tab is open or after a sync action.
        if not self.current_plan or self._sync_status_in_flight or self._busy:
            return
        if self.ids.audit_tab_manager.current != "sync_tab":
            return
        self._sync_status_in_flight = True
        service=SyncService(App.get_running_app().db)
        local=service.local_summary(self.current_plan["plan_id"],"AUDIT")
        plan_code = self.current_plan.get("plan_code") or self.current_plan.get("plan_details") or "-"
        self.ids.lbl_sync_device.text = f"{App.get_running_app().device_name} | Plan {plan_code}"
        self.ids.lbl_sync_plan.text = ""
        self._local_sync_summary = {
            "PENDING": int(local.get("PENDING", 0) or 0),
            "SYNCING": int(local.get("SYNCING", 0) or 0),
            "SYNCED": int(local.get("SYNCED", 0) or 0),
            "ERROR": int(local.get("ERROR", 0) or 0),
        }
        self._server_sync_summary = {"WAITING": 0, "PROCESSING": 0, "SUCCESS": 0, "ERROR": 0, "LOADED": False}
        self.ids.lbl_local_summary.text=f"รอส่ง {local['PENDING']} | ส่งแล้ว {local['SYNCED']} | ผิดพลาด {local['ERROR']}"
        self._update_sync_button_states()
        local_total = sum(int(local.get(name, 0) or 0) for name in ("PENDING", "SYNCING", "SYNCED", "ERROR"))
        if local_total <= 0:
            self._sync_status_in_flight = False
            self.ids.lbl_server_summary.text = "รอ Process 0 | สำเร็จ 0 | ผิดพลาด 0"
            self.ids.lbl_sync_status.text = "ยังไม่มีข้อมูล Sync"
            self.ids.btn_process_server.disabled = True
            return
        self._run(lambda:service.server_status(self._sync_url(),self.current_plan["plan_id"],"AUDIT"),self._apply_server)

    def send_sync(self, retry=False):
        service=SyncService(App.get_running_app().db); app=App.get_running_app(); self._busy=True; self._sync_buttons(True)
        fn=service.retry_error if retry else service.send
        self._run(lambda:fn(self._sync_url(),self.current_plan["plan_id"],app.device_name,getattr(app,"version","1.0.0"),transaction_type="AUDIT"),self._sync_done)

    def process_sync(self):
        service=SyncService(App.get_running_app().db); app=App.get_running_app(); self._busy=True; self._sync_buttons(True)
        self._run(lambda:service.process(self._sync_url(),self.current_plan["plan_id"],app.device_name,"AUDIT"),self._sync_done)

    def _apply_server(self,result):
        self._sync_status_in_flight = False
        waiting = int(result.get("waiting_count", 0) or 0)
        processing = int(result.get("processing_count", 0) or 0)
        success_count = int(result.get("success_count", 0) or 0)
        error_count = int(result.get("error_count", 0) or 0)
        self._server_sync_summary = {
            "WAITING": waiting,
            "PROCESSING": processing,
            "SUCCESS": success_count,
            "ERROR": error_count,
            "LOADED": True,
        }
        self.ids.lbl_server_summary.text=f"รอ Process {waiting} | สำเร็จ {success_count} | ผิดพลาด {error_count}"
        self.ids.lbl_sync_status.text=result.get("status_message","")
        self._update_sync_button_states()

    def _sync_done(self,result):
        self._busy = False
        self._sync_status_in_flight = False
        self.ids.lbl_sync_status.text = result.get("message") or result.get("status") or "สำเร็จ"
        self.refresh_sync()

    def _run(self,func,callback):
        def worker():
            try: result=func(); Clock.schedule_once(lambda dt:callback(result),0)
            except Exception as exc:
                error_message = str(exc)
                Clock.schedule_once(
                    lambda dt, message=error_message: self._sync_error(message),
                    0,
                )
        threading.Thread(target=worker,daemon=True).start()

    def _sync_error(self,message):
        self._busy = False
        self._sync_status_in_flight = False
        self.ids.lbl_sync_status.text = message
        self._update_sync_button_states()

    def _update_sync_button_states(self):
        if self._busy:
            self._sync_buttons(True)
            return

        local = self._local_sync_summary or {}
        server = self._server_sync_summary or {}
        pending = int(local.get("PENDING", 0) or 0)
        syncing = int(local.get("SYNCING", 0) or 0)
        local_error = int(local.get("ERROR", 0) or 0)
        waiting = int(server.get("WAITING", 0) or 0)
        processing = int(server.get("PROCESSING", 0) or 0)
        server_error = int(server.get("ERROR", 0) or 0)
        server_loaded = bool(server.get("LOADED", False))

        self.ids.btn_sync_now.disabled = pending <= 0 or syncing > 0
        self.ids.btn_retry_sync.disabled = (
            (local_error <= 0 and (not server_loaded or server_error <= 0))
            or syncing > 0
            or processing > 0
        )
        self.ids.btn_process_server.disabled = (
            not server_loaded or waiting <= 0 or processing > 0
        )
        self.ids.btn_refresh_sync.disabled = False

    def _sync_buttons(self, disabled):
        disabled = bool(disabled)

        # ID ต้องตรงกับปุ่มจริงใน audit_screen.kv
        for name in (
            "btn_sync_now",
            "btn_retry_sync",
            "btn_process_server",
            "btn_refresh_sync",
        ):
            button = self.ids.get(name)
            if button is not None:
                button.disabled = disabled

    def _sync_url(self):
        app=App.get_running_app(); return str(getattr(app,"api_url","") or getattr(app,"sync_url","") or "")

    # Methods named exactly like CountScreen so both KV layouts stay identical.
    def save_current_item(self):
        return self.save_current()

    def open_calculator(self):
        # ใช้ keypad ของระบบโดย focus ช่องจำนวน เหมือนหน้าจอ Count
        if not self.ids.txt_qty.disabled:
            self.ids.txt_qty.focus = True

    def switch_correction_mode(self):
        new_mode = "LOCATION" if self.correction_mode == "QTY" else "QTY"
        self.set_correction_mode(new_mode)
        if new_mode == "LOCATION":
            self.ids.btn_location_mode.text = "เปลี่ยนเป็นแก้ QTY"
            self.ids.btn_apply_location.width = "130dp"
            self.ids.btn_apply_location.opacity = 1
        else:
            self.ids.btn_location_mode.text = "เปลี่ยนเป็นแก้ LOC"
            self.ids.btn_apply_location.width = "0dp"
            self.ids.btn_apply_location.opacity = 0

    def open_location_correction(self):
        return self.apply_location_correction()

    def start_sync(self):
        return self.send_sync(False)

    def retry_sync(self):
        if self._busy or not self.current_plan:
            return
        service = SyncService(App.get_running_app().db)
        plan_id = self.current_plan["plan_id"]
        local = service.local_summary(plan_id, "AUDIT")
        local_error = int(local.get("ERROR", 0) or 0)
        server_error = int((self._server_sync_summary or {}).get("ERROR", 0) or 0)

        if local_error > 0:
            self.ids.lbl_sync_status.text = "กำลัง Retry Sync รายการ Error..."
            return self.send_sync(True)

        if server_error > 0:
            app = App.get_running_app()
            self._busy = True
            self._sync_buttons(True)
            self.ids.lbl_sync_status.text = "กำลัง Retry Process รายการ Error..."
            self._run(
                lambda: service.retry_process_error(
                    self._sync_url(), plan_id, app.device_name, "AUDIT"
                ),
                self._sync_done,
            )
            return

        self.ids.lbl_sync_status.text = "ไม่มีรายการ Error ที่ต้อง Retry"
        self._update_sync_button_states()

    def process_server_data(self):
        return self.process_sync()

    def load_sync_status(self):
        return self.refresh_sync()

    def go_back(self):
        if self.ids.audit_tab_manager.current != "audit_tab": self.switch_tab("audit_tab")
        elif self.manager: self.manager.current="main_menu"

    def _focus_scan(self): Clock.schedule_once(lambda dt:setattr(self.ids.txt_barcode,"focus",True),.1)
    def _dismiss_dialog(self):
        if self._dialog:
            try:self._dialog.dismiss()
            except Exception:pass
            self._dialog=None
    def _apply_thai_font(self, widget):
        """Compatibility only: ฟอนต์กำหนดตรง Widget/KV เพื่อไม่กระทบ Icon Font."""
        return

    @staticmethod
    def _fmt(value):
        try:
            n=float(value or 0); return str(int(n)) if n.is_integer() else f"{n:g}"
        except Exception:return str(value or 0)
