"""
=========================================================
Project : HWK_StockV1
File    : models/count_transaction.py

Count Transaction Model
=========================================================
"""

from dataclasses import dataclass
from enum import Enum


# =====================================================
# Transaction Type
# =====================================================
class TransactionType(Enum):

    COUNT = "COUNT"
    AUDIT = "AUDIT"


# =====================================================
# Duplicate Action
# =====================================================
class DuplicateAction(Enum):

    ADD = "ADD"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"


# =====================================================
# Count Transaction
# =====================================================
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

    def to_dict(self):

        return {
            "transaction_guid":
                self.transaction_guid,

            "plan_id":
                self.plan_id,

            "plan_detail_id":
                self.plan_detail_id,

            "item_id":
                self.item_id,

            "location_id":
                self.location_id,

            "barcode":
                self.barcode,

            "qty":
                self.qty,

            "checker":
                self.checker,

            "is_audit":
                0,

            "create_date":
                self.create_date
        }