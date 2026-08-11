"""
=========================================================
Project : HWK_StockV1
File    : services/download_service.py

Download Plan Service
=========================================================
"""

from __future__ import annotations

from typing import Any, Dict
import requests

from utils.http_json import decode_json_response, build_server_error, JsonResponseError

from repository.download_repository import DownloadRepository


class DownloadService:
    """
    รับผิดชอบ:

    1. เรียก DownloadPlan.ashx
    2. ตรวจสอบ HTTP Response
    3. ตรวจสอบ JSON Contract
    4. ส่งข้อมูลทั้งหมดเข้า DownloadRepository
    5. คืนผลสรุปให้ DownloadScreen

    Service จะไม่แปลงโครงสร้าง JSON อีกต่อไป
    เพราะ Server ส่งข้อมูลในรูปแบบที่ SQLite ใช้โดยตรงแล้ว
    """

    def __init__(self, db):
        self.db = db
        self.repository = DownloadRepository(db)

    # =====================================================
    # Download Plan
    # =====================================================

    def download_plan(
        self,
        download_url: str,
        plan_id: int,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Download Plan จาก Server และบันทึกลง SQLite

        Parameters
        ----------
        download_url:
            URL ของ DownloadPlan.ashx

        plan_id:
            Plan ID ที่ต้องการดาวน์โหลด

        timeout:
            Request timeout หน่วยวินาที

        Returns
        -------
        dict
            ผลการบันทึก เช่น

            {
                "success": True,
                "message": "Download plan สำเร็จ",
                "plan_id": 5176,
                "plan_code": "test_PT_102025",
                "item_count": 100,
                "barcode_count": 200,
                "location_count": 5,
                "detail_count": 100
            }
        """

        download_url = self._normalize_url(download_url)
        plan_id = self._validate_plan_id(plan_id)
        timeout = self._validate_timeout(timeout)

        payload = {
            "plan_id": plan_id,
        }

        try:
            response = requests.post(
                download_url,
                json=payload,
                timeout=timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )

        except requests.Timeout as exc:
            raise DownloadServiceError(
                f"หมดเวลารอ Server หลังจาก {timeout} วินาที"
            ) from exc

        except requests.ConnectionError as exc:
            raise DownloadServiceError(
                "ไม่สามารถเชื่อมต่อ Download Server ได้ "
                "กรุณาตรวจสอบ Wi-Fi, Server IP และ IIS"
            ) from exc

        except requests.RequestException as exc:
            raise DownloadServiceError(
                f"เกิดข้อผิดพลาดระหว่างเรียก Download Server: {exc}"
            ) from exc

        data = self._read_json_response(response)

        self._validate_server_response(
            response=response,
            data=data,
        )

        self._validate_download_package(data)

        try:
            save_result = self.repository.save_download_package(
                data
            )

        except Exception as exc:
            raise DownloadServiceError(
                f"บันทึกข้อมูล Download ลง SQLite ไม่สำเร็จ: {exc}"
            ) from exc

        result = self._build_result(
            package=data,
            save_result=save_result,
        )

        return result

    # =====================================================
    # Validate URL
    # =====================================================

    def _normalize_url(self, download_url: str) -> str:
        if download_url is None:
            raise DownloadServiceError(
                "ไม่พบ Download URL"
            )

        url = str(download_url).strip()

        if not url:
            raise DownloadServiceError(
                "Download URL เป็นค่าว่าง"
            )

        if not (
            url.lower().startswith("http://")
            or url.lower().startswith("https://")
        ):
            raise DownloadServiceError(
                "Download URL ต้องขึ้นต้นด้วย http:// หรือ https://"
            )

        return url

    # =====================================================
    # Validate Plan ID
    # =====================================================

    def _validate_plan_id(self, plan_id: int) -> int:
        try:
            value = int(plan_id)

        except (TypeError, ValueError) as exc:
            raise DownloadServiceError(
                "Plan ID ไม่ถูกต้อง"
            ) from exc

        if value <= 0:
            raise DownloadServiceError(
                "Plan ID ต้องมากกว่า 0"
            )

        return value

    # =====================================================
    # Validate Timeout
    # =====================================================

    def _validate_timeout(self, timeout: int) -> int:
        try:
            value = int(timeout)

        except (TypeError, ValueError):
            value = 120

        if value <= 0:
            value = 120

        return value

    # =====================================================
    # Read JSON
    # =====================================================

    def _read_json_response(
        self,
        response: requests.Response,
    ) -> Dict[str, Any]:
        try:
            return decode_json_response(response, require_object=True)
        except JsonResponseError as exc:
            raise DownloadServiceError(str(exc)) from exc

    # =====================================================
    # Validate Server Response
    # =====================================================

    def _validate_server_response(
        self,
        response: requests.Response,
        data: Dict[str, Any],
    ) -> None:
        success = bool(data.get("success", False))

        full_message = build_server_error(data, "Download Plan Error")

        if response.status_code >= 400:
            raise DownloadServiceError(
                full_message
                or (
                    "Server ตอบกลับด้วย HTTP Status "
                    f"{response.status_code}"
                )
            )

        if not success:
            raise DownloadServiceError(
                full_message
                or "Server แจ้งว่า Download Plan ไม่สำเร็จ"
            )

    # =====================================================
    # Validate Package
    # =====================================================

    def _validate_download_package(
        self,
        data: Dict[str, Any],
    ) -> None:
        required_keys = (
            "plan",
            "items",
            "barcodes",
            "locations",
            "details",
        )

        missing_keys = [
            key
            for key in required_keys
            if key not in data
        ]

        if missing_keys:
            raise DownloadServiceError(
                "ข้อมูลจาก Server ไม่ครบ ขาด: "
                + ", ".join(missing_keys)
            )

        plan = data.get("plan")

        if not isinstance(plan, dict):
            raise DownloadServiceError(
                "ข้อมูล plan ต้องเป็น JSON Object"
            )

        try:
            plan_id = int(plan.get("plan_id", 0))
        except (TypeError, ValueError):
            plan_id = 0

        if plan_id <= 0:
            raise DownloadServiceError(
                "ข้อมูล plan ไม่มี plan_id ที่ถูกต้อง"
            )

        list_keys = (
            "items",
            "barcodes",
            "locations",
            "details",
        )

        for key in list_keys:
            if not isinstance(data.get(key), list):
                raise DownloadServiceError(
                    f"ข้อมูล {key} ต้องเป็น JSON Array"
                )

        if len(data["details"]) == 0:
            raise DownloadServiceError(
                "Plan นี้ไม่มี Plan Detail"
            )

        self._validate_items(data["items"])
        self._validate_barcodes(data["barcodes"])
        self._validate_locations(data["locations"])
        self._validate_details(data["details"])

    # =====================================================
    # Validate Items
    # =====================================================

    def _validate_items(
        self,
        items: list,
    ) -> None:
        seen_item_ids = set()

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise DownloadServiceError(
                    f"items[{index}] ต้องเป็น JSON Object"
                )

            try:
                item_id = int(item.get("item_id", 0))
            except (TypeError, ValueError):
                item_id = 0

            item_code = str(
                item.get("item_code") or ""
            ).strip()

            if item_id <= 0:
                raise DownloadServiceError(
                    f"items[{index}] ไม่มี item_id ที่ถูกต้อง"
                )

            if not item_code:
                raise DownloadServiceError(
                    f"items[{index}] ไม่มี item_code"
                )

            if item_id in seen_item_ids:
                raise DownloadServiceError(
                    f"พบ item_id ซ้ำใน items: {item_id}"
                )

            seen_item_ids.add(item_id)

    # =====================================================
    # Validate Barcodes
    # =====================================================

    def _validate_barcodes(
        self,
        barcodes: list,
    ) -> None:
        seen_codes = set()

        for index, row in enumerate(barcodes):
            if not isinstance(row, dict):
                raise DownloadServiceError(
                    f"barcodes[{index}] ต้องเป็น JSON Object"
                )

            try:
                item_id = int(row.get("item_id", 0))
            except (TypeError, ValueError):
                item_id = 0

            barcode = str(
                row.get("barcode") or ""
            ).strip()

            if item_id <= 0:
                raise DownloadServiceError(
                    f"barcodes[{index}] ไม่มี item_id ที่ถูกต้อง"
                )

            if not barcode:
                raise DownloadServiceError(
                    f"barcodes[{index}] ไม่มี barcode"
                )

            barcode_key = (
                item_id,
                barcode,
            )

            if barcode_key in seen_codes:
                raise DownloadServiceError(
                    "พบ Barcode ซ้ำสำหรับ Item เดียวกัน: "
                    f"{barcode}"
                )

            seen_codes.add(barcode_key)

    # =====================================================
    # Validate Locations
    # =====================================================

    def _validate_locations(
        self,
        locations: list,
    ) -> None:
        seen_codes = set()

        for index, location in enumerate(locations):
            if not isinstance(location, dict):
                raise DownloadServiceError(
                    f"locations[{index}] ต้องเป็น JSON Object"
                )

            location_code = str(
                location.get("location_code") or ""
            ).strip()

            if not location_code:
                raise DownloadServiceError(
                    f"locations[{index}] ไม่มี location_code"
                )

            if location_code in seen_codes:
                raise DownloadServiceError(
                    f"พบ location_code ซ้ำ: {location_code}"
                )

            seen_codes.add(location_code)

    # =====================================================
    # Validate Details
    # =====================================================

    def _validate_details(
        self,
        details: list,
    ) -> None:
        seen_detail_ids = set()

        for index, detail in enumerate(details):
            if not isinstance(detail, dict):
                raise DownloadServiceError(
                    f"details[{index}] ต้องเป็น JSON Object"
                )

            try:
                plan_detail_id = int(
                    detail.get("plan_detail_id", 0)
                )
            except (TypeError, ValueError):
                plan_detail_id = 0

            try:
                plan_id = int(
                    detail.get("plan_id", 0)
                )
            except (TypeError, ValueError):
                plan_id = 0

            try:
                item_id = int(
                    detail.get("item_id", 0)
                )
            except (TypeError, ValueError):
                item_id = 0

            item_code = str(detail.get("item_code") or "").strip()

            if plan_detail_id <= 0:
                raise DownloadServiceError(
                    f"details[{index}] ไม่มี plan_detail_id "
                    "ที่ถูกต้อง"
                )

            if plan_id <= 0:
                raise DownloadServiceError(
                    f"details[{index}] ไม่มี plan_id ที่ถูกต้อง"
                )

            if item_id <= 0:
                raise DownloadServiceError(
                    f"details[{index}] ไม่มี item_id ที่ถูกต้อง"
                )

            if not item_code:
                raise DownloadServiceError(
                    f"details[{index}] ไม่มี item_code"
                )

            if plan_detail_id in seen_detail_ids:
                raise DownloadServiceError(
                    "พบ plan_detail_id ซ้ำ: "
                    f"{plan_detail_id}"
                )

            seen_detail_ids.add(plan_detail_id)

    # =====================================================
    # Result
    # =====================================================

    def _build_result(
        self,
        package: Dict[str, Any],
        save_result: Any,
    ) -> Dict[str, Any]:
        plan = package.get("plan") or {}
        summary = package.get("summary") or {}

        result: Dict[str, Any] = {
            "success": True,
            "message": str(
                package.get("message")
                or "Download plan สำเร็จ"
            ),
            "plan_id": int(
                plan.get("plan_id", 0)
            ),
            "plan_code": str(
                plan.get("plan_code") or ""
            ),
            "plan_status": str(
                plan.get("plan_status") or ""
            ),
            "item_count": int(
                summary.get(
                    "item_count",
                    len(package.get("items") or []),
                )
            ),
            "barcode_count": int(
                summary.get(
                    "barcode_count",
                    len(package.get("barcodes") or []),
                )
            ),
            "location_count": int(
                summary.get(
                    "location_count",
                    len(package.get("locations") or []),
                )
            ),
            "detail_count": int(
                summary.get(
                    "detail_count",
                    len(package.get("details") or []),
                )
            ),
        }

        if isinstance(save_result, dict):
            result.update(save_result)

            result["success"] = True

            if not result.get("message"):
                result["message"] = "Download plan สำเร็จ"

        return result


class DownloadServiceError(Exception):
    """
    Exception สำหรับแสดงข้อความผิดพลาดจาก DownloadService
    ไปยังหน้าจอโดยตรง
    """

    pass