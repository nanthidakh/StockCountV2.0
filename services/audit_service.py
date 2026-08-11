"""Audit business service."""
from models.count_transaction import CountTransaction
from repository.audit_repository import AuditRepository


class AuditService:
    def __init__(self, db):
        self.repo = AuditRepository(db)

    def get_current_plan(self):
        plan = self.repo.get_current_plan()
        if not plan:
            return {"status": "NO_PLAN", "message": "กรุณา Download Plan ก่อน"}
        if int(plan.get("total_items") or 0) <= 0:
            return {"status": "PLAN_EMPTY", "message": "ใบงานไม่มีรายการ", "plan": plan}
        return {"status": "READY", "plan": plan}

    def scan_location(self, plan_id, scan_value):
        location = self.repo.find_location(plan_id, scan_value)
        return {"status": "SUCCESS", "location": location} if location else {"status": "LOCATION_NOT_FOUND"}

    def prepare_item(self, plan_id, location_id, scan_value):
        item = self.repo.find_item(scan_value)
        if not item:
            return {"status": "ITEM_NOT_FOUND"}
        detail = self.repo.get_audit_detail(plan_id, item["item_id"], location_id)
        if not detail:
            any_detail = self.repo.get_audit_detail_any_location(plan_id, item["item_id"])
            if any_detail:
                return {"status": "WRONG_LOCATION", "item": item, "detail": any_detail}
            return {"status": "UNEXPECTED_ITEM", "item": item}
        audit_round = int(detail.get("audit_round") or 0)
        if audit_round <= 0:
            # audit_count is the last completed round from server.
            audit_round = max(1, int(detail.get("audit_count") or 0) + 1)
            detail["audit_round"] = audit_round
        duplicate = self.repo.find_duplicate(plan_id, item["item_id"], location_id, audit_round)
        return {"status": "READY", "item": item, "detail": detail, "duplicate": duplicate}

    def create_local_plan_detail(self, plan_id, item_id, location_id):
        self.repo.create_local_plan_detail(plan_id, item_id, location_id)
        detail = self.repo.get_audit_detail(plan_id, item_id, location_id)
        if detail:
            detail["audit_round"] = max(1, int(detail.get("audit_count") or 0) + 1)
        return detail

    def save_audit(self, detail, item, location_id, scanned_barcode, qty, auditor, duplicate_mode="ADD"):
        tx = CountTransaction.create_audit(
            detail["plan_id"], detail["plan_detail_id"], item["item_id"],
            location_id, scanned_barcode, qty, auditor, detail["audit_round"],
        )
        return self.repo.save_audit(tx, duplicate_mode)

    def get_recent(self, plan_id, limit=15):
        return self.repo.get_recent_audits(plan_id, limit)

    def correct_qty(self, history_id, qty, auditor):
        qty = float(qty)
        if qty < 0: raise ValueError("จำนวนต้องไม่ติดลบ")
        return self.repo.correct_qty(history_id, qty, auditor)

    def correct_locations(self, history_ids, location_code, plan_id, auditor):
        location = self.repo.find_location(plan_id, location_code)
        if not location: raise ValueError("ไม่พบ Location ใหม่")
        return self.repo.correct_locations(history_ids, location["location_id"], auditor)
