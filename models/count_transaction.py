"""
=========================================================
Project : HWK_StockV1
File    : models/count_transaction.py
Shared Count / Audit Transaction Model
=========================================================
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4


class TransactionType(str, Enum):
    COUNT = "COUNT"
    AUDIT = "AUDIT"


class OperationType(str, Enum):
    INSERT = "INSERT"
    UPDATE_QTY = "UPDATE_QTY"
    UPDATE_LOCATION = "UPDATE_LOCATION"


@dataclass
class CountTransaction:
    transaction_guid: str
    plan_id: int
    plan_detail_id: int
    item_id: int
    location_id: str
    barcode: str
    qty: float
    checker: str
    create_date: str
    transaction_type: TransactionType = TransactionType.COUNT
    operation_type: OperationType = OperationType.INSERT
    audit_round: int = 0
    reference_transaction_guid: Optional[str] = None

    @classmethod
    def create_count(cls, plan_id, plan_detail_id, item_id, location_id, barcode, qty, checker):
        return cls._create(
            plan_id, plan_detail_id, item_id, location_id, barcode, qty, checker,
            TransactionType.COUNT, OperationType.INSERT, 0, None,
        )

    @classmethod
    def create_audit(
        cls, plan_id, plan_detail_id, item_id, location_id, barcode,
        qty, auditor, audit_round,
    ):
        audit_round = int(audit_round or 0)
        if audit_round <= 0:
            raise ValueError("Audit Round ต้องมากกว่า 0")
        return cls._create(
            plan_id, plan_detail_id, item_id, location_id, barcode, qty, auditor,
            TransactionType.AUDIT, OperationType.INSERT, audit_round, None,
        )

    @classmethod
    def create_correction(
        cls, source: "CountTransaction", operation_type: OperationType,
        qty: Optional[float] = None, location_id: Optional[str] = None,
    ):
        if operation_type not in (OperationType.UPDATE_QTY, OperationType.UPDATE_LOCATION):
            raise ValueError("Correction operation ไม่ถูกต้อง")
        return cls._create(
            source.plan_id,
            source.plan_detail_id,
            source.item_id,
            location_id if location_id is not None else source.location_id,
            source.barcode,
            source.qty if qty is None else qty,
            source.checker,
            source.transaction_type,
            operation_type,
            source.audit_round,
            source.transaction_guid,
        )

    @classmethod
    def _create(
        cls, plan_id, plan_detail_id, item_id, location_id, barcode, qty, checker,
        transaction_type, operation_type, audit_round, reference_guid,
    ):
        qty = float(qty)
        if qty < 0:
            raise ValueError("จำนวนต้องไม่ติดลบ")
        checker = str(checker or "").strip() or "UNKNOWN_DEVICE"
        return cls(
            transaction_guid=str(uuid4()),
            plan_id=int(plan_id),
            plan_detail_id=int(plan_detail_id),
            item_id=int(item_id),
            location_id=str(location_id or "").strip(),
            barcode=str(barcode or "").strip(),
            qty=qty,
            checker=checker,
            create_date=datetime.now().isoformat(timespec="seconds"),
            transaction_type=TransactionType(transaction_type),
            operation_type=OperationType(operation_type),
            audit_round=int(audit_round or 0),
            reference_transaction_guid=reference_guid,
        )

    def to_dict(self) -> Dict[str, Any]:
        is_audit = self.transaction_type == TransactionType.AUDIT
        result = {
            "transaction_guid": self.transaction_guid,
            "reference_transaction_guid": self.reference_transaction_guid,
            "transaction_type": self.transaction_type.value,
            "operation_type": self.operation_type.value,
            "plan_id": self.plan_id,
            "plan_detail_id": self.plan_detail_id,
            "item_id": self.item_id,
            "location_id": self.location_id,
            "barcode": self.barcode,
            "qty": self.qty,
            "checker": self.checker,
            "is_audit": 1 if is_audit else 0,
            "audit_round": self.audit_round,
            "create_date": self.create_date,
            "transaction_date": self.create_date,
            "modified_at": self.create_date,
        }
        if is_audit:
            result.update({
                "qty_audit": self.qty,
                "auditor": self.checker,
                "audit_date": self.create_date,
            })
        else:
            result.update({
                "qty_on_hand": self.qty,
                "check_date": self.create_date,
            })
        return result
