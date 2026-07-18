from sqlalchemy.orm import Session

from app.models.config import ProductConfig
from app.models.credit import CREDIT_TYPE_CONSUME, CreditTransaction
from app.models.user import User


def get_product_config(db: Session) -> ProductConfig:
    config = db.get(ProductConfig, 1)
    if config is None:
        config = ProductConfig(id=1)
        db.add(config)
        db.flush()
    return config


def consume_credits(db: Session, user: User, amount: int, note: str, job_id: int | None = None) -> None:
    if amount <= 0:
        return
    if user.credits < amount:
        from fastapi import HTTPException

        raise HTTPException(status_code=402, detail="Insufficient credits")
    user.credits -= amount
    db.add(
        CreditTransaction(
            user_id=user.id,
            type=CREDIT_TYPE_CONSUME,
            amount=-amount,
            balance_after=user.credits,
            note=note,
            job_id=job_id,
        )
    )
