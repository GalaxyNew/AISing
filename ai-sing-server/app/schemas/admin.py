from datetime import datetime

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    token: str
    username: str


class AdminPasswordUpdate(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class AdminUserResponse(BaseModel):
    id: int
    username: str
    phone: str
    credits: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    phone: str = ""
    credits: int = 480


class AdminUserUpdate(BaseModel):
    username: str | None = None
    phone: str | None = None
    credits: int | None = None
    status: str | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class AdminCreditAdd(BaseModel):
    amount: int = Field(gt=0)
    note: str = "后台充值"


class AdminConfigUpdate(BaseModel):
    signup_bonus_credits: int = Field(ge=0)
    voice_train_cost: int = Field(ge=0)
    song_process_cost: int = Field(ge=0)
    recharge_price_per_credit: int = Field(ge=0)


class AdminSupportUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    qr_code_url: str = ""
