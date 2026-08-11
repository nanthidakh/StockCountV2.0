"""
=========================================================
Project : HWK_StockV1
File    : services/correction_service.py

Correction Service
=========================================================
"""

from models.count_transaction import CountTransaction
from repository.count_repository import CountRepository


class CorrectionService:
    def __init__(self, db):
        self.count_repo = CountRepository(db)

    @staticmethod
    def _value(source, key, default=None):
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)

    def correct_qty(self, old_transaction, new_qty, checker=None):
        """แก้รายการ COUNT เดิมที่ยังไม่ Sync โดยไม่สร้าง Transaction/Queue ใหม่."""
        if old_transaction is None:
            raise ValueError("กรุณาเลือกรายการที่ต้องการแก้ไข")

        try:
            new_qty = float(new_qty)
        except (TypeError, ValueError) as exc:
            raise ValueError("จำนวนใหม่ไม่ถูกต้อง") from exc

        if new_qty < 0:
            raise ValueError("จำนวนใหม่ต้องไม่น้อยกว่า 0")

        history_id = self._value(old_transaction, "history_id")
        if history_id is None:
            raise ValueError("ไม่พบ History ID ของรายการที่เลือก")

        checker = (
            str(checker or "").strip()
            or str(self._value(old_transaction, "checker", "")).strip()
            or "ANDROID"
        )

        return self.count_repo.update_pending_qty(
            history_id=int(history_id),
            new_qty=new_qty,
            checker=checker,
        )

    def correct_locations(self, transactions, new_location_code, checker=None):
        new_location_code = str(new_location_code or "").strip()
        if not new_location_code:
            raise ValueError("กรุณาระบุ Location ใหม่")

        rows = [dict(row) for row in (transactions or [])]
        if not rows:
            raise ValueError("กรุณาเลือกรายการที่ต้องการแก้ไข Location")

        plan_ids = {int(self._value(row, "plan_id")) for row in rows}
        if len(plan_ids) != 1:
            raise ValueError("รายการที่เลือกต้องอยู่ใน Plan เดียวกัน")

        plan_id = plan_ids.pop()
        location = self.count_repo.find_location(plan_id, new_location_code)
        if not location:
            raise ValueError(f"ไม่พบ Location: {new_location_code} ใน Plan นี้")

        history_ids = []
        for row in rows:
            history_id = self._value(row, "history_id")
            if history_id is None:
                raise ValueError("ไม่พบ History ID ของรายการที่เลือก")
            history_ids.append(int(history_id))

        checker = str(checker or "").strip() or "ANDROID"

        return self.count_repo.correct_locations(
            plan_id=plan_id,
            history_ids=history_ids,
            new_location_id=int(location["location_id"]),
            new_location_code=str(location["location_code"] or "").strip(),
            checker=checker,
        )

