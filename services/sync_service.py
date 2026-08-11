"""
=========================================================
Project : HWK_StockV1
File    : services/sync_service.py

Android Sync Service with per-send Batch GUID
=========================================================
"""

from urllib.parse import urlsplit, urlunsplit

import requests

from repository.sync_repository import SyncRepository
from utils.http_json import decode_json_response, build_server_error, JsonResponseError


class SyncService:
    def __init__(self, db, timeout=120):
        self.repo = SyncRepository(db)
        self.timeout = int(timeout or 120)

    def local_summary(self, plan_id, transaction_type="COUNT"):
        return self.repo.get_local_summary(plan_id, transaction_type)

    def get_device_id(self):
        return self.repo.get_or_create_device_id()

    def get_current_batch_guid(self, plan_id, transaction_type="COUNT"):
        return self.repo.get_current_batch_guid(plan_id, transaction_type)

    def send(
        self,
        sync_url,
        plan_id,
        device_name,
        app_version="1.0.0",
        batch_size=500,
        include_error=False,
        transaction_type="COUNT",
    ):
        endpoint = self._endpoint(sync_url, "SyncCount.ashx")
        queues = self.repo.get_sendable(plan_id, batch_size, include_error, transaction_type)
        if not queues:
            return {
                "status": "NO_DATA",
                "sent": 0,
                "success": 0,
                "error": 0,
                "sync_batch_guid": self.get_current_batch_guid(plan_id, transaction_type),
            }

        # การกดส่งแต่ละครั้งคือ Batch ใหม่ เพื่อไม่ให้ยอด Server ปนรอบเก่า
        sync_batch_guid = self.repo.create_batch_guid(plan_id, transaction_type)
        guids = [str(row["transaction_guid"]) for row in queues]
        self.repo.assign_batch(guids, sync_batch_guid)
        self.repo.mark_syncing(guids)

        payload = {
            "device_id": self.get_device_id(),
            "device_name": str(device_name or "UNKNOWN_DEVICE"),
            "app_version": str(app_version or "1.0.0"),
            "sync_batch_guid": sync_batch_guid,
            "transactions": [self.repo.build_transaction(row) for row in queues],
        }

        try:
            response = requests.post(endpoint, json=payload, timeout=self.timeout)
            result = decode_json_response(response, require_object=True)
            if response.status_code >= 400:
                raise RuntimeError(build_server_error(result, f"HTTP {response.status_code}"))
        except Exception as exc:
            self.repo.restore_pending(guids, str(exc))
            raise RuntimeError(f"ส่งข้อมูลไป Server ไม่สำเร็จ: {exc}") from exc

        result_by_guid = {
            str(item.get("transaction_guid")): item
            for item in (result.get("results") or [])
        }
        success_count = 0
        error_count = 0
        for guid in guids:
            item = result_by_guid.get(guid)
            if item and bool(item.get("success")):
                self.repo.mark_synced(guid)
                success_count += 1
            else:
                message = (item or {}).get("message") or "Server ไม่คืนผลของ Transaction"
                self.repo.mark_error(guid, message)
                error_count += 1

        return {
            "status": "SUCCESS" if error_count == 0 else "PARTIAL",
            "sent": len(guids),
            "success": success_count,
            "error": error_count,
            "sync_batch_guid": sync_batch_guid,
            "server": result,
        }

    def retry_error(
        self,
        sync_url,
        plan_id,
        device_name,
        app_version="1.0.0",
        batch_size=500,
        transaction_type="COUNT",
    ):
        return self.send(
            sync_url,
            plan_id,
            device_name,
            app_version,
            batch_size=batch_size,
            include_error=True,
            transaction_type=transaction_type,
        )

    def process(self, sync_url, plan_id, device_name, transaction_type="COUNT", retry_error=False):
        sync_batch_guid = self.get_current_batch_guid(plan_id, transaction_type)
        if not sync_batch_guid:
            raise RuntimeError("ยังไม่มี Batch ที่ส่งขึ้น Server กรุณากดส่งข้อมูลก่อน")

        endpoint = self._endpoint(sync_url, "ProcessCount.ashx")
        payload = {
            "device_id": self.get_device_id(),
            "device_name": str(device_name or "UNKNOWN_DEVICE"),
            "plan_id": int(plan_id),
            "sync_batch_guid": sync_batch_guid,
            "retry_error": bool(retry_error),
        }
        response = requests.post(endpoint, json=payload, timeout=self.timeout)
        result = decode_json_response(response, require_object=True)
        if response.status_code >= 400:
            raise RuntimeError(build_server_error(result, f"HTTP {response.status_code}"))
        if not bool(result.get("success")):
            errors = result.get("validation_errors") or []
            details = []
            for item in errors[:5]:
                code = str(item.get("error_code") or "VALIDATION_ERROR")
                message = str(item.get("error_message") or "")
                staging_id = item.get("staging_id")
                details.append(
                    f"#{staging_id} {code}: {message}"
                    if staging_id is not None
                    else f"{code}: {message}"
                )

            base_message = result.get("message") or "Process ไม่สำเร็จ"
            if details:
                base_message += " | " + " ; ".join(details)
                if len(errors) > 5:
                    base_message += f" ; และอีก {len(errors) - 5} รายการ"

            raise RuntimeError(base_message)
        return result

    def retry_process_error(self, sync_url, plan_id, device_name, transaction_type="COUNT"):
        """Reprocess only Server staging rows in ERROR for the current batch."""
        return self.process(
            sync_url,
            plan_id,
            device_name,
            transaction_type=transaction_type,
            retry_error=True,
        )

    def server_status(self, sync_url, plan_id, transaction_type="COUNT"):
        sync_batch_guid = self.get_current_batch_guid(plan_id, transaction_type)
        if not sync_batch_guid:
            return {
                "success": True,
                "has_batch": False,
                "waiting_count": 0,
                "processing_count": 0,
                "success_count": 0,
                "error_count": 0,
                "status_message": "ยังไม่มี Batch ที่ส่งขึ้น Server",
            }

        endpoint = self._endpoint(sync_url, "GetSyncStatus.ashx")
        payload = {
            "device_id": self.get_device_id(),
            "plan_id": int(plan_id),
            "sync_batch_guid": sync_batch_guid,
        }
        response = requests.post(endpoint, json=payload, timeout=self.timeout)
        result = decode_json_response(response, require_object=True)
        if response.status_code >= 400:
            raise RuntimeError(build_server_error(result, f"HTTP {response.status_code}"))
        if not bool(result.get("success")):
            raise RuntimeError(result.get("message") or "อ่านสถานะ Server ไม่สำเร็จ")

        return {
            "success": True,
            "has_batch": bool(result.get("has_batch", True)),
            "waiting_count": int(result.get("waiting_count", result.get("waiting", 0)) or 0),
            "processing_count": int(result.get("processing_count", result.get("processing", 0)) or 0),
            "success_count": int(result.get("success_count", result.get("processed_success", 0)) or 0),
            "error_count": int(result.get("error_count", result.get("processed_error", 0)) or 0),
            "last_received": result.get("last_received"),
            "last_processed": result.get("last_processed"),
            "status_message": result.get("status_message") or "",
        }

    @staticmethod
    def _endpoint(base_url, filename):
        value = str(base_url or "").strip()
        if not value:
            raise ValueError("ยังไม่ได้ตั้งค่า Sync URL")
        parts = urlsplit(value)
        path = parts.path or "/"
        last = path.rsplit("/", 1)[-1]
        if "." in last:
            path = path.rsplit("/", 1)[0] + "/" + filename
        else:
            path = path.rstrip("/") + "/" + filename
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
