"""
=========================================================
Project : HWK_StockV1
File    : screens/download_screen.py

Download Plan Screen
=========================================================
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import BooleanProperty, NumericProperty, StringProperty

from screens.base_screen import BaseScreen
from services.download_service import (
    DownloadService,
    DownloadServiceError,
)


class DownloadScreen(BaseScreen):
    """
    หน้าจอ Download Plan

    ขั้นตอนการทำงาน:

    1. รับ Plan ID
    2. ตรวจสอบ Config
    3. เรียก DownloadService ผ่าน Background Thread
    4. Service เรียก DownloadPlan.ashx
    5. Repository บันทึกข้อมูลลง SQLite
    6. กลับมาอัปเดตหน้าจอผ่าน Clock.schedule_once()
    """

    is_downloading = BooleanProperty(False)

    progress_value = NumericProperty(0)

    status_text = StringProperty("พร้อมดาวน์โหลด")

    result_text = StringProperty("")

    downloaded_plan_id = NumericProperty(0)

    downloaded_plan_code = StringProperty("")

    item_count = NumericProperty(0)

    barcode_count = NumericProperty(0)

    location_count = NumericProperty(0)

    detail_count = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._download_thread: Optional[
            threading.Thread
        ] = None

    # =====================================================
    # Screen Events
    # =====================================================
    def go_main(
        self
    ):
        if self.is_downloading:
            self._show_error(
                "กรุณารอให้ Download เสร็จก่อน"
            )
            return

        if self.manager is None:
            return

        self.manager.current = "main_menu"
    def on_pre_enter(self, *args):
        """
        ทำงานก่อนแสดงหน้าจอ
        """

        self._reset_screen_state(
            clear_plan_id=False
        )

        # แสดงข้อมูล Plan ที่มีอยู่ใน SQLite ทันที
        # เพื่อไม่ให้หน้าจอกลับไปแสดง 0 ทุกครั้งที่เข้าหน้า Download
        self._load_existing_download_summary()

        Clock.schedule_once(
            self._focus_plan_field,
            0.2,
        )

    def _load_existing_download_summary(self):
        """อ่านจำนวนข้อมูลของ Plan ล่าสุดที่มีอยู่จริงใน SQLite."""

        app = App.get_running_app()
        if app is None or not self._has_database(app):
            return

        connection = None
        should_close = False

        try:
            db = app.db

            if hasattr(db, "get_connection"):
                connection = db.get_connection()
                should_close = True
            elif hasattr(db, "connect"):
                connection = db.connect()
            else:
                return

            if connection is None:
                return

            def table_exists(table_name):
                row = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                ).fetchone()
                return row is not None

            if not table_exists("tb_plan"):
                return

            plan_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(tb_plan)"
                ).fetchall()
            }

            code_column = (
                "plan_code"
                if "plan_code" in plan_columns
                else "plan_name"
                if "plan_name" in plan_columns
                else None
            )
            order_column = (
                "download_date"
                if "download_date" in plan_columns
                else "plan_id"
            )
            code_select = code_column if code_column else "''"

            plan_row = connection.execute(
                f"""
                SELECT plan_id, {code_select} AS plan_code
                FROM tb_plan
                ORDER BY
                    CASE WHEN {order_column} IS NULL THEN 1 ELSE 0 END,
                    {order_column} DESC,
                    plan_id DESC
                LIMIT 1
                """
            ).fetchone()

            if plan_row is None:
                return

            plan_id = self._safe_int(plan_row[0])
            plan_code = str(plan_row[1] or "").strip()

            detail_count = 0
            item_count = 0
            barcode_count = 0
            location_count = 0

            if table_exists("tb_plan_detail"):
                detail_count = self._safe_int(
                    connection.execute(
                        "SELECT COUNT(*) FROM tb_plan_detail WHERE plan_id=?",
                        (plan_id,),
                    ).fetchone()[0]
                )
                item_count = self._safe_int(
                    connection.execute(
                        "SELECT COUNT(DISTINCT item_id) FROM tb_plan_detail WHERE plan_id=?",
                        (plan_id,),
                    ).fetchone()[0]
                )

                if table_exists("tb_barcode"):
                    barcode_count = self._safe_int(
                        connection.execute(
                            """
                            SELECT COUNT(*)
                            FROM tb_barcode b
                            WHERE EXISTS
                            (
                                SELECT 1
                                FROM tb_plan_detail d
                                WHERE d.plan_id=?
                                  AND d.item_id=b.item_id
                            )
                            """,
                            (plan_id,),
                        ).fetchone()[0]
                    )

            if table_exists("tb_location"):
                location_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(tb_location)"
                    ).fetchall()
                }
                if "plan_id" in location_columns:
                    location_count = self._safe_int(
                        connection.execute(
                            "SELECT COUNT(*) FROM tb_location WHERE plan_id=?",
                            (plan_id,),
                        ).fetchone()[0]
                    )
                elif table_exists("tb_plan_detail"):
                    location_count = self._safe_int(
                        connection.execute(
                            """
                            SELECT COUNT(DISTINCT location_id)
                            FROM tb_plan_detail
                            WHERE plan_id=?
                              AND location_id IS NOT NULL
                              AND TRIM(CAST(location_id AS TEXT))<>''
                            """,
                            (plan_id,),
                        ).fetchone()[0]
                    )

            self.downloaded_plan_id = plan_id
            self.downloaded_plan_code = plan_code
            self.item_count = item_count
            self.barcode_count = barcode_count
            self.location_count = location_count
            self.detail_count = detail_count
            self.status_text = "พบข้อมูลที่ดาวน์โหลดไว้ในเครื่อง"
            self.result_text = (
                f"Plan ID: {plan_id}\n"
                f"Plan: {plan_code}\n"
                f"สินค้า: {item_count:,} รายการ\n"
                f"Barcode: {barcode_count:,} รายการ\n"
                f"Location: {location_count:,} รายการ\n"
                f"Plan Detail: {detail_count:,} รายการ"
            )

            plan_field = self._get_widget("txt_plan")
            if plan_field is not None and not str(plan_field.text or "").strip():
                plan_field.text = str(plan_id)

            self._update_widget_state()
            self._set_status_widget(self.status_text)
            self._set_result_widget(self.result_text)

        except Exception as exc:
            # การอ่าน Summary เดิมไม่ควรทำให้เข้าหน้า Download ไม่ได้
            print(f"Load existing download summary failed: {exc}")

        finally:
            if should_close and connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def on_leave(self, *args):
        """
        ไม่ยกเลิก Thread ระหว่างออกจากหน้าจอ

        Thread จะทำงานต่อจนจบ และบันทึก SQLite ให้เสร็จ
        """

        self._clear_plan_focus()

    # =====================================================
    # Start Download
    # =====================================================

    def start_download(self):
        """
        เริ่ม Download จากปุ่มบนหน้าจอ
        """

        if self.is_downloading:
            self._show_error(
                "กำลังดาวน์โหลดข้อมูลอยู่"
            )
            return

        plan_id = self._read_plan_id()

        if plan_id is None:
            return

        app = App.get_running_app()

        if app is None:
            self._show_error(
                "ไม่พบ Application Instance"
            )
            return

        download_url = self._get_download_url(app)

        if not download_url:
            self._show_error(
                "ยังไม่ได้ตั้งค่า Download URL\n"
                "กรุณาไปที่หน้าตั้งค่าระบบก่อน"
            )
            return

        if not self._has_database(app):
            self._show_error(
                "ไม่พบการเชื่อมต่อ SQLite"
            )
            return

        timeout = self._get_timeout(app)

        self._prepare_download_ui(
            plan_id=plan_id
        )

        self._download_thread = threading.Thread(
            target=self._download_worker,
            args=(
                app,
                download_url,
                plan_id,
                timeout,
            ),
            daemon=True,
            name=f"DownloadPlan-{plan_id}",
        )

        self._download_thread.start()

    # =====================================================
    # Background Worker
    # =====================================================

    def _download_worker(
        self,
        app,
        download_url: str,
        plan_id: int,
        timeout: int,
    ):
        """
        ทำงานใน Background Thread

        ห้ามแก้ไข Widget โดยตรงใน Function นี้
        ต้องใช้ Clock.schedule_once เท่านั้น
        """

        try:
            self._schedule_progress(
                value=20,
                status="กำลังเชื่อมต่อ Server...",
            )

            service = DownloadService(
                app.db
            )

            self._schedule_progress(
                value=40,
                status="กำลังดาวน์โหลดข้อมูล Plan...",
            )

            result = service.download_plan(
                download_url=download_url,
                plan_id=plan_id,
                timeout=timeout,
            )

            self._schedule_progress(
                value=85,
                status="กำลังตรวจสอบข้อมูลที่บันทึก...",
            )

            Clock.schedule_once(
                lambda dt: self._download_success(
                    result
                ),
                0,
            )

        except DownloadServiceError as exc:
            message = str(exc).strip()

            Clock.schedule_once(
                lambda dt, error=message:
                    self._download_failed(error),
                0,
            )

        except Exception as exc:
            message = str(exc).strip()

            if not message:
                message = exc.__class__.__name__

            Clock.schedule_once(
                lambda dt, error=message:
                    self._download_failed(
                        "เกิดข้อผิดพลาดที่ไม่คาดคิด\n"
                        + error
                    ),
                0,
            )

    # =====================================================
    # Download Success
    # =====================================================

    def _download_success(
        self,
        result: Dict[str, Any],
    ):
        
        
        verified = bool(
            result.get("verified", False)
            )

        if not verified:
            self._download_failed(
                    "Download สำเร็จแต่ตรวจสอบข้อมูล SQLite ไม่ผ่าน"
            )
            return
        """
        ทำงานบน Main Thread หลัง Download สำเร็จ
        """

        self.is_downloading = False
        self.progress_value = 100

        self.downloaded_plan_id = self._safe_int(
            result.get("plan_id")
        )

        self.downloaded_plan_code = str(
            result.get("plan_code") or ""
        ).strip()

        self.item_count = self._safe_int(
            result.get("item_count")
        )

        self.barcode_count = self._safe_int(
            result.get("barcode_count")
        )

        self.location_count = self._safe_int(
            result.get("location_count")
        )

        self.detail_count = self._safe_int(
            result.get("detail_count")
        )

        self.status_text = "Download สำเร็จ"

        self.result_text = (
            f"Plan ID: {self.downloaded_plan_id}\n"
            f"Plan: {self.downloaded_plan_code}\n"
            f"สินค้า: {self.item_count:,} รายการ\n"
            f"Barcode: {self.barcode_count:,} รายการ\n"
            f"Location: {self.location_count:,} รายการ\n"
            f"Plan Detail: {self.detail_count:,} รายการ"
        )

        self._update_widget_state()

        self._hide_loading()

        self._set_progress_widget(100)

        self._set_status_widget(
            "Download สำเร็จ"
        )

        self._set_result_widget(
            self.result_text
        )

        self._show_success(
            title="สำเร็จ",
            message=(
                "ดาวน์โหลด Plan สำเร็จ\n\n"
                f"Plan ID: {self.downloaded_plan_id}\n"
                f"Plan: {self.downloaded_plan_code}\n"
                f"สินค้า: {self.item_count:,} รายการ\n"
                f"Barcode: {self.barcode_count:,} รายการ\n"
                f"Location: {self.location_count:,} รายการ\n"
                f"รายละเอียด: {self.detail_count:,} รายการ"
            ),
        )

        self._clear_plan_focus()

    # =====================================================
    # Download Failed
    # =====================================================

    def _download_failed(
        self,
        message: str,
    ):
        """
        ทำงานบน Main Thread เมื่อ Download ไม่สำเร็จ
        """

        self.is_downloading = False
        self.progress_value = 0
        self.status_text = "Download ไม่สำเร็จ"
        self.result_text = ""

        self._update_widget_state()

        self._hide_loading()

        self._set_progress_widget(0)

        self._set_status_widget(
            "Download ไม่สำเร็จ"
        )

        self._set_result_widget("")

        self._show_error(
            message
            or "Download Plan ไม่สำเร็จ"
        )

        Clock.schedule_once(
            self._focus_plan_field,
            0.3,
        )

    # =====================================================
    # UI Preparation
    # =====================================================

    def _prepare_download_ui(
        self,
        plan_id: int,
    ):
        self.is_downloading = True
        self.progress_value = 5
        self.status_text = (
            f"กำลังเตรียม Download Plan {plan_id}"
        )
        self.result_text = ""

        self.downloaded_plan_id = 0
        self.downloaded_plan_code = ""

        self.item_count = 0
        self.barcode_count = 0
        self.location_count = 0
        self.detail_count = 0

        self._clear_plan_focus()

        self._update_widget_state()

        self._show_loading(
            "กำลังดาวน์โหลด Plan..."
        )

        self._set_progress_widget(5)

        self._set_status_widget(
            self.status_text
        )

        self._set_result_widget("")

    def _reset_screen_state(
        self,
        clear_plan_id: bool = False,
    ):
        if self.is_downloading:
            return

        self.progress_value = 0
        self.status_text = "พร้อมดาวน์โหลด"
        self.result_text = ""

        self.downloaded_plan_id = 0
        self.downloaded_plan_code = ""

        self.item_count = 0
        self.barcode_count = 0
        self.location_count = 0
        self.detail_count = 0

        if clear_plan_id:
            plan_field = self._get_widget(
                "txt_plan"
            )

            if plan_field is not None:
                plan_field.text = ""

        self._update_widget_state()

    def clear_form(self):
        """
        เรียกจากปุ่มล้างข้อมูลได้
        """

        if self.is_downloading:
            self._show_error(
                "ไม่สามารถล้างข้อมูลขณะกำลังดาวน์โหลด"
            )
            return

        self._reset_screen_state(
            clear_plan_id=True
        )

        self._set_progress_widget(0)

        self._set_status_widget(
            "พร้อมดาวน์โหลด"
        )

        self._set_result_widget("")

        Clock.schedule_once(
            self._focus_plan_field,
            0.2,
        )

    # =====================================================
    # Plan ID
    # =====================================================

    def _read_plan_id(
        self,
    ) -> Optional[int]:
        plan_field = self._get_widget(
            "txt_plan"
        )

        if plan_field is None:
            self._show_error(
                "ไม่พบช่องกรอก Plan ID: txt_plan"
            )
            return None

        text = str(
            getattr(plan_field, "text", "")
            or ""
        ).strip()

        if not text:
            self._show_error(
                "กรุณากรอก Plan ID"
            )

            Clock.schedule_once(
                self._focus_plan_field,
                0.2,
            )

            return None

        try:
            plan_id = int(text)

        except (TypeError, ValueError):
            self._show_error(
                "Plan ID ต้องเป็นตัวเลขเท่านั้น"
            )

            Clock.schedule_once(
                self._focus_plan_field,
                0.2,
            )

            return None

        if plan_id <= 0:
            self._show_error(
                "Plan ID ต้องมากกว่า 0"
            )

            Clock.schedule_once(
                self._focus_plan_field,
                0.2,
            )

            return None

        return plan_id

    # =====================================================
    # App Config
    # =====================================================

    def _get_download_url(
        self,
        app
    ) -> str:
        """
        อ่าน Download URL จาก Config

        รองรับ:
        - URL เต็มใน app.download_url
        - API Root ใน app.api_url
        """

        download_url = str(
            getattr(
                app,
                "download_url",
                ""
            ) or ""
        ).strip()

        if download_url:
            return download_url.rstrip("/")

        api_url = str(
            getattr(
                app,
                "api_url",
                ""
            ) or ""
        ).strip()

        if not api_url:
            return ""

        api_url = api_url.rstrip("/")

        if api_url.lower().endswith(
            "downloadplan.ashx"
        ):
            return api_url

        return (
            api_url +
            "/DownloadPlan.ashx"
        )
    def _get_timeout(
        self,
        app,
    ) -> int:
        value = getattr(
            app,
            "timeout",
            120,
        )

        try:
            timeout = int(value)

        except (TypeError, ValueError):
            timeout = 120

        if timeout <= 0:
            timeout = 120

        return timeout

    def _has_database(
        self,
        app,
    ) -> bool:
        return (
            hasattr(app, "db")
            and app.db is not None
        )

    # =====================================================
    # Thread-safe Progress
    # =====================================================

    def _schedule_progress(
        self,
        value: int,
        status: str,
    ):
        Clock.schedule_once(
            lambda dt: self._apply_progress(
                value=value,
                status=status,
            ),
            0,
        )

    def _apply_progress(
        self,
        value: int,
        status: str,
    ):
        self.progress_value = value
        self.status_text = status

        self._set_progress_widget(value)

        self._set_status_widget(status)

    # =====================================================
    # Widgets
    # =====================================================

    def _get_widget(
        self,
        widget_id: str,
    ):
        try:
            return self.ids.get(widget_id)

        except Exception:
            return None

    def _update_widget_state(
        self,
    ):
        button = self._get_widget(
            "btn_download"
        )

        if button is not None:
            try:
                button.disabled = (
                    self.is_downloading
                )
            except Exception:
                pass

        clear_button = self._get_widget(
            "btn_clear"
        )

        if clear_button is not None:
            try:
                clear_button.disabled = (
                    self.is_downloading
                )
            except Exception:
                pass

        plan_field = self._get_widget(
            "txt_plan"
        )

        if plan_field is not None:
            try:
                plan_field.disabled = (
                    self.is_downloading
                )
            except Exception:
                pass

    def _set_progress_widget(
        self,
        value: int,
    ):
        progress = self._get_widget(
            "progress_bar"
        )

        if progress is None:
            progress = self._get_widget(
                "progress"
            )

        if progress is not None:
            try:
                progress.value = value
            except Exception:
                pass

        if hasattr(self, "set_progress"):
            try:
                self.set_progress(value)
            except Exception:
                pass

    def _set_status_widget(
        self,
        text: str,
    ):
        label = self._get_widget(
            "lbl_status"
        )

        if label is not None:
            try:
                label.text = text
            except Exception:
                pass

        if hasattr(self, "set_status"):
            try:
                self.set_status(text)
            except Exception:
                pass

    def _set_result_widget(
        self,
        text: str,
    ):
        label = self._get_widget(
            "lbl_result"
        )

        if label is None:
            label = self._get_widget(
                "lbl_detail"
            )

        if label is not None:
            try:
                label.text = text
            except Exception:
                pass

        if hasattr(self, "set_label"):
            try:
                self.set_label(text)
            except Exception:
                pass

    # =====================================================
    # Loading
    # =====================================================

    def _show_loading(
        self,
        message: str,
    ):
        if hasattr(self, "show_loading"):
            try:
                self.show_loading(message)
            except Exception:
                pass

    def _hide_loading(
        self,
    ):
        if hasattr(self, "hide_loading"):
            try:
                self.hide_loading()
            except Exception:
                pass

    # =====================================================
    # Dialog
    # =====================================================

    def _show_error(
        self,
        message: str,
    ):
        if hasattr(self, "show_error"):
            try:
                self.show_error(message)
                return
            except Exception:
                pass

        app = App.get_running_app()

        if (
            app is not None
            and hasattr(app, "show_alert")
        ):
            try:
                app.show_alert(
                    "เกิดข้อผิดพลาด",
                    message,
                )
                return
            except Exception:
                pass

        print(
            "[DOWNLOAD ERROR]",
            message,
        )

    def _show_success(
        self,
        title: str,
        message: str,
    ):
        app = App.get_running_app()

        if (
            app is not None
            and hasattr(app, "show_alert")
        ):
            try:
                app.show_alert(
                    title,
                    message,
                )
                return
            except Exception:
                pass

        if hasattr(self, "show_success"):
            try:
                self.show_success(message)
                return
            except Exception:
                pass

        print(
            "[DOWNLOAD SUCCESS]",
            message,
        )

    # =====================================================
    # Focus
    # =====================================================

    def _focus_plan_field(
        self,
        *args,
    ):
        if self.is_downloading:
            return

        plan_field = self._get_widget(
            "txt_plan"
        )

        if plan_field is None:
            return

        try:
            plan_field.disabled = False
            plan_field.focus = False

            Clock.schedule_once(
                lambda dt: self._apply_plan_focus(
                    plan_field
                ),
                0.1,
            )

        except Exception:
            pass

    def _apply_plan_focus(
        self,
        plan_field,
    ):
        if self.is_downloading:
            return

        try:
            plan_field.focus = True

            if hasattr(plan_field, "cursor"):
                text_length = len(
                    getattr(
                        plan_field,
                        "text",
                        "",
                    )
                )

                plan_field.cursor = (
                    text_length,
                    0,
                )

        except Exception:
            pass

    def _clear_plan_focus(
        self,
    ):
        plan_field = self._get_widget(
            "txt_plan"
        )

        if plan_field is not None:
            try:
                plan_field.focus = False
            except Exception:
                pass

    # =====================================================
    # Navigation
    # =====================================================

    def go_back(self):
        """
        กลับหน้าก่อนหน้า

        ถ้ากำลัง Download จะไม่ออกจากหน้าจอ
        เพื่อป้องกันผู้ใช้เข้าใจว่า Download ถูกยกเลิก
        """

        if self.is_downloading:
            self._show_error(
                "กรุณารอให้ Download เสร็จก่อน"
            )
            return

        if hasattr(super(), "go_back"):
            try:
                super().go_back()
                return
            except Exception:
                pass

        manager = getattr(
            self,
            "manager",
            None,
        )

        if manager is None:
            return

        if manager.has_screen(
            "main_menu"
        ):
            manager.current = "main_menu"

        elif manager.has_screen(
            "main_menu_screen"
        ):
            manager.current = "main_menu_screen"

        elif manager.has_screen(
            "menu_screen"
        ):
            manager.current = "menu_screen"

    # =====================================================
    # Helpers
    # =====================================================

    def _safe_int(
        self,
        value: Any,
    ) -> int:
        if value is None or value == "":
            return 0

        try:
            return int(value)

        except (TypeError, ValueError):
            try:
                return int(float(value))

            except (TypeError, ValueError):
                return 0