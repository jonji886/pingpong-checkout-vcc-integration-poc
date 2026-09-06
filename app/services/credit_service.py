from __future__ import annotations

from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.credit import available_balance
from ..models import CreditAccount, CreditHold, CreditLedger
from .common import new_id, utcnow


class CreditService:
    @staticmethod
    def ensure_account(db: Session, user_id: str) -> CreditAccount:
        account = db.query(CreditAccount).filter_by(user_id=user_id).first()
        if account:
            return account
        account = CreditAccount(id=new_id("acct"), user_id=user_id, credit_unit="USD_CREDIT", posted_balance=Decimal("0"), available_balance=Decimal("0"))
        try:
            with db.begin_nested():
                db.add(account)
                db.flush()
        except IntegrityError:
            account = db.query(CreditAccount).filter_by(user_id=user_id).one()
        return account

    @staticmethod
    def held_amount(db: Session, account_id: str) -> Decimal:
        value = db.query(CreditHold).filter(CreditHold.account_id == account_id, CreditHold.status == "HELD").with_entities(CreditHold.credit_amount).all()
        return sum((Decimal(row[0]) for row in value), Decimal("0"))

    @classmethod
    def refresh_available(cls, db: Session, account: CreditAccount) -> None:
        account.available_balance = available_balance(Decimal(account.posted_balance), cls.held_amount(db, account.id))
        account.updated_at = utcnow()

    @classmethod
    def add_topup(cls, db: Session, *, user_id: str, amount: Decimal, payment_id: str) -> bool:
        account = cls.ensure_account(db, user_id)
        key = "TOPUP:" + payment_id
        if db.query(CreditLedger).filter_by(idempotency_key=key).first():
            cls.refresh_available(db, account)
            return False
        entry = CreditLedger(id=new_id("ledger"), account_id=account.id, entry_type="TOPUP", credit_amount=amount, fiat_amount=amount, fiat_currency="USD", pricing_rule_version="P0_USD_1_TO_1", reference_type="PAYMENT", reference_id=payment_id, idempotency_key=key)
        try:
            with db.begin_nested():
                db.add(entry)
                db.flush()
                account.posted_balance = Decimal(account.posted_balance) + amount
                cls.refresh_available(db, account)
            return True
        except IntegrityError:
            account = db.query(CreditAccount).filter_by(user_id=user_id).one()
            cls.refresh_available(db, account)
            return False

    @classmethod
    def create_hold(cls, db: Session, *, user_id: str, refund_id: str, amount: Decimal):
        account = cls.ensure_account(db, user_id)
        cls.refresh_available(db, account)
        if Decimal(account.available_balance) < amount:
            return None
        hold = CreditHold(id=new_id("hold"), account_id=account.id, refund_id=refund_id, credit_amount=amount, status="HELD")
        db.add(hold)
        db.flush()
        cls.refresh_available(db, account)
        return hold

    @classmethod
    def settle_hold(cls, db: Session, hold: CreditHold, *, refund_id: str, amount: Decimal) -> None:
        if hold.status != "HELD":
            return
        account = db.query(CreditAccount).filter_by(id=hold.account_id).one()
        if not db.query(CreditLedger).filter_by(idempotency_key="REFUND_REVERSAL:" + refund_id).first():
            try:
                with db.begin_nested():
                    db.add(CreditLedger(id=new_id("ledger"), account_id=account.id, entry_type="REFUND_REVERSAL", credit_amount=-amount, fiat_amount=amount, fiat_currency="USD", pricing_rule_version="P0_USD_1_TO_1", reference_type="REFUND", reference_id=refund_id, idempotency_key="REFUND_REVERSAL:" + refund_id))
                    db.flush()
                    account.posted_balance = Decimal(account.posted_balance) - amount
            except IntegrityError:
                pass
        hold.status = "SETTLED"
        hold.settled_at = utcnow()
        cls.refresh_available(db, account)

    @classmethod
    def release_hold(cls, db: Session, hold: CreditHold) -> None:
        if hold.status != "HELD":
            return
        hold.status = "RELEASED"
        hold.released_at = utcnow()
        account = db.query(CreditAccount).filter_by(id=hold.account_id).one()
        cls.refresh_available(db, account)
