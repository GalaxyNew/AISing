from datetime import datetime

from pydantic import BaseModel


class ProductConfigResponse(BaseModel):
    signup_bonus_credits: int
    voice_train_cost: int
    song_process_cost: int
    recharge_price_per_credit: int


class SupportInfoResponse(BaseModel):
    name: str
    qr_code_url: str


class CreditTransactionResponse(BaseModel):
    id: int
    type: str
    amount: int
    balance_after: int
    note: str
    job_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileResponse(BaseModel):
    user_id: int
    username: str
    phone: str
    credits: int
    config: ProductConfigResponse
    support: SupportInfoResponse
