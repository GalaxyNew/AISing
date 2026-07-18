from datetime import datetime

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: int
    user_id: int | None
    type: str
    status: str
    progress: int
    input_path: str
    output_path: str | None
    metadata_json: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
