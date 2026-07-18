from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.core.database import get_db
from app.models.config import SupportInfo
from app.models.credit import CreditTransaction
from app.models.user import User
from app.schemas.commerce import (
    CreditTransactionResponse,
    ProductConfigResponse,
    ProfileResponse,
    SupportInfoResponse,
)
from app.services.credits import get_product_config


router = APIRouter(prefix="/api", tags=["commerce"])


def get_support_info(db: Session) -> SupportInfo:
    support = db.get(SupportInfo, 1)
    if support is None:
        support = SupportInfo(id=1)
        db.add(support)
        db.flush()
    return support


def config_response(db: Session) -> ProductConfigResponse:
    config = get_product_config(db)
    return ProductConfigResponse(
        signup_bonus_credits=config.signup_bonus_credits,
        voice_train_cost=config.voice_train_cost,
        song_process_cost=config.song_process_cost,
        recharge_price_per_credit=config.recharge_price_per_credit,
    )


def support_response(db: Session) -> SupportInfoResponse:
    support = get_support_info(db)
    return SupportInfoResponse(name=support.name, qr_code_url=support.qr_code_path)


@router.get("/profile", response_model=ProfileResponse)
def profile(db: Session = Depends(get_db), user: User = Depends(current_user)) -> ProfileResponse:
    return ProfileResponse(
        user_id=user.id,
        username=user.username,
        phone=user.phone,
        credits=user.credits,
        config=config_response(db),
        support=support_response(db),
    )


@router.get("/credit-transactions", response_model=list[CreditTransactionResponse])
def credit_transactions(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CreditTransactionResponse]:
    rows = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(100)
    ).all()
    return [CreditTransactionResponse.model_validate(row) for row in rows]


@router.get("/public/support", response_model=SupportInfoResponse)
def public_support(db: Session = Depends(get_db)) -> SupportInfoResponse:
    return support_response(db)


@router.get("/public/config", response_model=ProductConfigResponse)
def public_config(db: Session = Depends(get_db)) -> ProductConfigResponse:
    return config_response(db)
