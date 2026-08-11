"""
=========================================================
Project : HWK_StockV1
File    : services/count_service.py
Count Service
=========================================================
"""

from models.count_transaction import CountTransaction
from repository.count_repository import CountRepository


class CountService:
    def __init__(self, db):
        self.db = db
        self.count_repo = CountRepository(db)

    def get_current_plan(self):
        plan = self.db.query_one(
            """
            SELECT
                p.*,
                COALESCE(NULLIF(p.plan_details, ''), p.plan_code, 'Plan ' || p.plan_id) AS plan_name,
                COUNT(pd.plan_detail_id) AS total_items
            FROM tb_plan AS p
            LEFT JOIN tb_plan_detail AS pd ON pd.plan_id = p.plan_id
            GROUP BY p.plan_id
            ORDER BY COALESCE(p.download_date, p.update_date, p.create_date) DESC,
                     p.plan_id DESC
            LIMIT 1
            """
        )
        if not plan:
            return {"status": "NO_PLAN", "message": "ยังไม่มีแผนตรวจนับในเครื่อง"}
        if int(plan.get("total_items") or 0) <= 0:
            return {"status": "PLAN_EMPTY", "message": "พบแผนตรวจนับ แต่ยังไม่มีรายการสินค้า", "plan": plan}
        return {"status": "READY", "message": "ข้อมูลพร้อมตรวจนับ", "plan": plan}

    def scan_location(self, plan_id, location_code):
        location_code = str(location_code or "").strip()
        if not location_code:
            return {"status": "LOCATION_REQUIRED"}
        location = self.count_repo.find_location(plan_id, location_code)
        if not location:
            return {"status": "LOCATION_NOT_FOUND"}
        return {"status": "SUCCESS", "location": location}

    def find_location(self, plan_id, scan_value):
        return self.count_repo.find_location(plan_id, scan_value)

    def prepare_item(self, plan_id, location_id, barcode):
        barcode = str(barcode or "").strip()
        item = self.count_repo.find_item(barcode)
        if not item:
            return {"status": "ITEM_NOT_FOUND"}
        detail = self.count_repo.get_plan_detail(plan_id, item["item_id"], location_id)
        if not detail:
            any_detail = self.count_repo.get_plan_detail_any_location(plan_id, item["item_id"])
            if any_detail:
                return {"status": "WRONG_LOCATION", "item": item, "detail": any_detail}
            return {"status": "UNEXPECTED_ITEM", "item": item}
        return {"status": "READY", "item": item, "detail": detail}

    def create_local_plan_detail(self, plan_id, item_id, location_id):
        detail_id = self.count_repo.create_local_plan_detail(plan_id, item_id, location_id)
        return self.count_repo.get_plan_detail(plan_id, item_id, location_id)

    def save_count(self, plan_id, plan_detail_id, item_id, location_id, barcode, qty, checker):
        try:
            qty = float(qty)
            if qty < 0:
                raise ValueError("จำนวนต้องไม่ติดลบ")
            transaction = CountTransaction.create_count(
                plan_id=plan_id,
                plan_detail_id=plan_detail_id,
                item_id=item_id,
                location_id=location_id,
                barcode=barcode,
                qty=qty,
                checker=checker,
            )
            return self.count_repo.save_count(transaction)
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def scan_item(self, plan_id, location_id, barcode, qty, checker):
        prepared = self.prepare_item(plan_id, location_id, barcode)
        if prepared.get("status") != "READY":
            return prepared
        item = prepared["item"]
        detail = prepared["detail"]
        saved = self.save_count(
            plan_id, detail["plan_detail_id"], item["item_id"],
            location_id, barcode, qty, checker,
        )
        if not saved.get("success"):
            return {"status": "ERROR", **saved}
        return {"status": "SUCCESS", "saved": saved, "item": item, "detail": detail}

    def get_recent_counts(self, plan_id, limit=5):
        try:
            return self.count_repo.get_recent_counts(int(plan_id), max(1, int(limit)))
        except (TypeError, ValueError):
            return []
