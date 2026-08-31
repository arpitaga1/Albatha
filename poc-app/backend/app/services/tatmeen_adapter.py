"""
Tatmeen Service Adapter — per the spec:

    "For the POC, if an actual Tatmeen API is not available, create a
    Tatmeen Service Adapter with realistic mock data. The application
    should behave as if it is communicating with Tatmeen."

Everything outside this module (the pipeline) only ever calls
`TatmeenAdapter.check_item()` / `check_sscc_hierarchy()` — never queries
TatmeenRecord/SSCCRecord directly. A real Tatmeen API integration later
only requires rewriting this module's internals (e.g. an HTTP call instead
of a DB query); the pipeline and every rule in validation_engine.py stay
untouched.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import SSCCRecord, TatmeenRecord


@dataclass
class TatmeenCheckResult:
    record: TatmeenRecord | None
    failed: bool = False          # True = "Tatmeen Validation Failed" (system could not complete the check)
    failure_reason: str | None = None
    simulated: bool = False       # True = record was randomly generated, not a real seeded lookup — see check_item


class TatmeenAdapter:
    def __init__(self, db: Session):
        self.db = db

    def check_item(
        self, gtin: str | None, batch: str, invoice_number: str, invoice_qty: int | None = None,
    ) -> TatmeenCheckResult:
        """
        Looks up a GTIN+Batch in the (simulated) Tatmeen database.

        Match GTIN+Batch scoped to the same invoice first (keeps the
        seeded demo flows and the two pinned real-invoice fixtures below
        exact and unambiguous), then fall back to GTIN+Batch alone,
        invoice-agnostic — Tatmeen in reality is a national database
        indexed by product identity, not by which specific invoice
        happens to reference it (fixed in Round 18 after the exact-
        invoice-number requirement blocked real uploaded invoices from
        ever finding a match).

        Two real invoice fixtures are pinned with dedicated seeded rows
        (see seed_data.py) and always resolve deterministically:
        TEST-INV-001 (Test_Invoice_Item1_Item2.pdf — Item 1 reported,
        Item 2 not) and 206204905 (Invoice_ProductA96_ProductC20.pdf —
        both items reported).

        Per user directive: for every OTHER GTIN+Batch/invoice combination
        — there being no real Tatmeen configured for this POC — genuinely
        RANDOMIZE reported vs. not-reported on each check, rather than the
        previous behavior of deterministically treating anything unseeded
        as "not reported." A fresh coin flip on every call, not cached, so
        re-running the same photo/invoice can legitimately show a
        different result — that's the honest behavior for "no real
        backing system," not a bug.
        """
        try:
            record = (
                self.db.query(TatmeenRecord)
                .filter(TatmeenRecord.invoice_number == invoice_number)
                .filter(TatmeenRecord.batch == batch)
                .filter((TatmeenRecord.gtin == gtin) | (TatmeenRecord.gtin.is_(None)))
                .first()
            )
            if record is None:
                record = (
                    self.db.query(TatmeenRecord)
                    .filter(TatmeenRecord.batch == batch)
                    .filter((TatmeenRecord.gtin == gtin) | (TatmeenRecord.gtin.is_(None)))
                    .first()
                )
            if record is not None:
                return TatmeenCheckResult(record=record)
            return TatmeenCheckResult(record=self._random_record(gtin, batch, invoice_number, invoice_qty), simulated=True)
        except Exception as e:  # pragma: no cover — "Tatmeen Validation Failed" per spec §9
            return TatmeenCheckResult(record=None, failed=True, failure_reason=str(e))

    @staticmethod
    def _random_record(gtin: str | None, batch: str, invoice_number: str, invoice_qty: int | None) -> TatmeenRecord:
        """
        A plain in-memory TatmeenRecord (never added to the DB session —
        it's a one-off simulated answer, not a persisted fact) with a
        genuinely random reported/not-reported outcome. When reported,
        reported_qty is set to exactly satisfy invoice_qty so the random
        outcome reads as a clean reported-vs-not-reported result rather
        than also randomly failing the separate quantity check for an
        unrelated reason the user didn't ask for.
        """
        reported = random.choice([True, False])
        return TatmeenRecord(
            gtin=gtin, batch=batch, serial=None, invoice_number=invoice_number,
            reported=reported, reported_qty=(invoice_qty or 0) if reported else 0,
            sscc=None, sscc_reported=False,
            reporting_date="2026-08-20" if reported else None,
        )

    def check_sscc_hierarchy(self, invoice_number: str) -> list[SSCCRecord]:
        try:
            return (
                self.db.query(SSCCRecord)
                .filter(SSCCRecord.invoice_number == invoice_number)
                .all()
            )
        except Exception:  # pragma: no cover
            return []
