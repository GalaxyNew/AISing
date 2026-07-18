from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.admin import Admin
from app.models.config import SupportInfo
from app.models.credit import CREDIT_TYPE_RECHARGE, CreditTransaction
from app.models.user import User
from app.schemas.admin import (
    AdminCreditAdd,
    AdminConfigUpdate,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPasswordReset,
    AdminPasswordUpdate,
    AdminSupportUpdate,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
)
from app.schemas.commerce import ProductConfigResponse, SupportInfoResponse
from app.schemas.oss import PresignUploadRequest, PresignUploadResponse
from app.services.credits import get_product_config
from app.services.oss_storage import OssStorageError, OssStorageService
from app.services.security import hash_password, make_token, verify_password


router = APIRouter(prefix="/api/admin", tags=["admin"])
oss_storage = OssStorageService()


def current_admin(authorization: str = Header(""), db: Session = Depends(get_db)) -> Admin:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization.removeprefix("Bearer ").strip()
    admin = db.scalars(select(Admin).where(Admin.active_token == token)).first()
    if admin is None:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return admin


@router.post("/oss/presign-upload", response_model=PresignUploadResponse)
def admin_presign_upload(
    payload: PresignUploadRequest,
    admin: Admin = Depends(current_admin),
) -> PresignUploadResponse:
    try:
        return PresignUploadResponse.model_validate(
            oss_storage.presign_upload(payload.category, payload.filename, payload.content_type, owner_id=f"admin-{admin.id}")
        )
    except OssStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> AdminLoginResponse:
    admin = db.scalars(select(Admin).where(Admin.username == payload.username.strip())).first()
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    admin.active_token = make_token()
    db.commit()
    db.refresh(admin)
    return AdminLoginResponse(token=admin.active_token, username=admin.username)


@router.post("/password")
def update_admin_password(
    payload: AdminPasswordUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> dict[str, bool]:
    if not verify_password(payload.old_password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid old password")
    admin.password_hash = hash_password(payload.new_password)
    admin.active_token = make_token()
    db.commit()
    return {"ok": True}


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    phone: str = "",
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> list[AdminUserResponse]:
    stmt = select(User).order_by(User.created_at.desc()).limit(200)
    if phone.strip():
        stmt = select(User).where(User.phone.contains(phone.strip())).order_by(User.created_at.desc()).limit(200)
    return [AdminUserResponse.model_validate(user) for user in db.scalars(stmt).all()]


@router.post("/users", response_model=AdminUserResponse)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> AdminUserResponse:
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        phone=payload.phone.strip(),
        credits=payload.credits,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.put("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.username is not None:
        user.username = payload.username.strip()
    if payload.phone is not None:
        user.phone = payload.phone.strip()
    if payload.credits is not None:
        user.credits = payload.credits
    if payload.status is not None:
        user.status = payload.status
    db.commit()
    db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> dict[str, bool]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(payload.password)
    user.active_token = None
    db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/credits", response_model=AdminUserResponse)
def add_user_credits(
    user_id: int,
    payload: AdminCreditAdd,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> AdminUserResponse:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.credits += payload.amount
    db.add(
        CreditTransaction(
            user_id=user.id,
            type=CREDIT_TYPE_RECHARGE,
            amount=payload.amount,
            balance_after=user.credits,
            note=payload.note,
        )
    )
    db.commit()
    db.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.get("/credit-transactions")
def list_credit_transactions(
    transaction_type: str = "",
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> list[dict]:
    stmt = select(CreditTransaction).order_by(CreditTransaction.created_at.desc()).limit(300)
    if transaction_type.strip():
        stmt = (
            select(CreditTransaction)
            .where(CreditTransaction.type == transaction_type.strip())
            .order_by(CreditTransaction.created_at.desc())
            .limit(300)
        )
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "type": row.type,
            "amount": row.amount,
            "balance_after": row.balance_after,
            "note": row.note,
            "job_id": row.job_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in db.scalars(stmt).all()
    ]


@router.get("/config", response_model=ProductConfigResponse)
def get_admin_config(
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> ProductConfigResponse:
    config = get_product_config(db)
    return ProductConfigResponse(
        signup_bonus_credits=config.signup_bonus_credits,
        voice_train_cost=config.voice_train_cost,
        song_process_cost=config.song_process_cost,
        recharge_price_per_credit=config.recharge_price_per_credit,
    )


@router.put("/config", response_model=ProductConfigResponse)
def update_admin_config(
    payload: AdminConfigUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> ProductConfigResponse:
    config = get_product_config(db)
    config.signup_bonus_credits = payload.signup_bonus_credits
    config.voice_train_cost = payload.voice_train_cost
    config.song_process_cost = payload.song_process_cost
    config.recharge_price_per_credit = payload.recharge_price_per_credit
    db.commit()
    db.refresh(config)
    return ProductConfigResponse(
        signup_bonus_credits=config.signup_bonus_credits,
        voice_train_cost=config.voice_train_cost,
        song_process_cost=config.song_process_cost,
        recharge_price_per_credit=config.recharge_price_per_credit,
    )


def get_admin_support(db: Session) -> SupportInfo:
    support = db.get(SupportInfo, 1)
    if support is None:
        support = SupportInfo(id=1)
        db.add(support)
        db.flush()
    return support


@router.get("/support", response_model=SupportInfoResponse)
def get_support(
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> SupportInfoResponse:
    support = get_admin_support(db)
    return SupportInfoResponse(name=support.name, qr_code_url=support.qr_code_path)


@router.put("/support", response_model=SupportInfoResponse)
def update_support(
    payload: AdminSupportUpdate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> SupportInfoResponse:
    support = get_admin_support(db)
    support.name = payload.name.strip()
    support.qr_code_path = payload.qr_code_url.strip()
    db.commit()
    db.refresh(support)
    return SupportInfoResponse(name=support.name, qr_code_url=support.qr_code_path)


@router.post("/support/qr-code", response_model=SupportInfoResponse)
async def upload_support_qr_code(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(current_admin),
) -> SupportInfoResponse:
    settings = get_settings()
    target_dir = settings.data_dir / "support"
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "qr.png").suffix or ".png"
    target = target_dir / f"support_qr{suffix}"
    target.write_bytes(await file.read())
    support = get_admin_support(db)
    support.qr_code_path = str(target)
    db.commit()
    db.refresh(support)
    return SupportInfoResponse(name=support.name, qr_code_url=support.qr_code_path)
