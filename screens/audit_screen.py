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

    def on_enter(self, *args):
        self.selected_recent_rows = {}
        self.current_location = None
        self.current_item = None
        self.current_detail = None
        self.ids.audit_tab_manager.current = "audit_tab"
        self._set_tab("audit_tab")
        self._load_device()
        # บังคับ Font ภาษาไทยให้ Widget ทั้งหน้าจอ รวม Widget ที่ Theme สร้างภายใน
        Clock.schedule_once(lambda dt: self._apply_thai_font(self), 0)
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
        self.ids.btn_change_location.disabled = not enabled
        self.ids.btn_calculator.disabled = not enabled

    def process_scan(self, scan_value):
        scan_value = str(scan_value or "").strip()
        self.ids.txt_barcode.text = ""
        if not scan_value or not self.current_plan:
            self._focus_scan(); return
        if self.current_location is None:
            self.scan_location(scan_value)
        else:
            self.scan_item(scan_value)

    def scan_location(self, scan_value):
        result = AuditService(App.get_running_app().db).scan_location(self.current_plan["plan_id"], scan_value)
        if result["status"] != "SUCCESS":
            self.ids.lbl_status.text = "ไม่พบ Location ในใบงาน"
            self._focus_scan(); return
        self.current_location = result["location"]
        code = self.current_location.get("location_code") or self.current_location.get("location_id")
        self.ids.lbl_location.text = str(code)
        self.ids.lbl_status.text = "ยิง Barcode หรือกรอกรหัสสินค้า"
        self._clear_item()
        self._focus_scan()

    def scan_item(self, scan_value):
        result = AuditService(App.get_running_app().db).prepare_item(
            self.current_plan["plan_id"], self.current_location["location_id"], scan_value,
        )
        status = result["status"]
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

        server_audit = self.current_detail.get("server_qty_audit")
        if server_audit is None:
            server_audit = self.current_detail.get("qty_audit")

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
        Clock.schedule_once(lambda dt: self._apply_thai_font(self._dialog), 0)

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

    def reset_location(self):
        self.current_location = None
        self.ids.lbl_location.text = "กรุณายิง Barcode Location"
        self._clear_item(); self._focus_scan()

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
        Clock.schedule_once(lambda dt: self._apply_thai_font(self._dialog), 0)

    def _apply_qty(self, row, text):
        try:
            AuditService(App.get_running_app().db).correct_qty(row["history_id"], text, App.get_running_app().device_name)
            self._dismiss_dialog(); self.ids.lbl_status.text="สร้าง Queue แก้ Qty Audit แล้ว"; self.load_recent(); self.refresh_sync()
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
        Clock.schedule_once(lambda dt: self._apply_thai_font(self._dialog), 0)

    def _apply_location(self, code):
        try:
            result=AuditService(App.get_running_app().db).correct_locations(
                list(self.selected_recent_rows),code,self.current_plan["plan_id"],App.get_running_app().device_name)
            self._dismiss_dialog(); self.selected_recent_rows={}; self.ids.lbl_status.text=f"สร้าง Queue แก้ Location {result['updated']} รายการ"; self.load_recent(); self.refresh_sync()
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
        self.ids.lbl_local_summary.text=f"รอส่ง {local['PENDING']} | ส่งแล้ว {local['SYNCED']} | ผิดพลาด {local['ERROR']}"
        self.ids.btn_sync_now.disabled=local['PENDING']<=0 or self._busy
        self.ids.btn_retry_sync.disabled=local['ERROR']<=0 or self._busy
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
        self.ids.lbl_server_summary.text=f"รอ Process {result.get('waiting_count',0)} | สำเร็จ {result.get('success_count',0)} | ผิดพลาด {result.get('error_count',0)}"
        self.ids.lbl_sync_status.text=result.get("status_message","")
        self.ids.btn_process_server.disabled=int(result.get("waiting_count",0))<=0 or self._busy

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
        self._sync_buttons(False)

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
        return self.send_sync(True)

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
        """ตั้ง ThaiFont ให้ Widget และ Child ที่รองรับ font_name/font_name_hint_text."""
        if widget is None:
            return

        for property_name in ("font_name", "font_name_hint_text"):
            if hasattr(widget, property_name):
                try:
                    setattr(widget, property_name, "ThaiFont")
                except Exception:
                    pass

        for child in getattr(widget, "children", []) or []:
            self._apply_thai_font(child)

    @staticmethod
    def _fmt(value):
        try:
            n=float(value or 0); return str(int(n)) if n.is_integer() else f"{n:g}"
        except Exception:return str(value or 0)
