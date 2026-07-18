from pathlib import Path
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import current_user
from app.models.job import JOB_STATUS_SUCCESS, JOB_TYPE_SONG_PROCESS, JOB_TYPE_VOICE_TRAIN
from app.models.credit import CreditTransaction
from app.models.user import User
from app.schemas.job import JobResponse
from app.schemas.oss import (
    PresignUploadRequest,
    PresignUploadResponse,
    SongUploadCompleteRequest,
    UploadedObject,
)
from app.services.credits import consume_credits, get_product_config
from app.services.oss_storage import OssStorageError, OssStorageService
from app.services.queue import QueueService
from app.services.storage import StorageService


router = APIRouter(prefix="/api/jobs", tags=["jobs"])
oss_router = APIRouter(prefix="/api/oss", tags=["oss"])
storage = StorageService()
oss_storage = OssStorageService()
queue = QueueService()
logger = logging.getLogger(__name__)


@oss_router.post("/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    payload: PresignUploadRequest,
    user: User = Depends(current_user),
) -> PresignUploadResponse:
    try:
        return PresignUploadResponse.model_validate(
            oss_storage.presign_upload(payload.category, payload.filename, payload.content_type, owner_id=user.id)
        )
    except OssStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/voice-train", response_model=JobResponse)
async def create_voice_train_job(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    config = get_product_config(db)
    input_path = await storage.save_upload(file, "voice_train")
    job = queue.create_job(db, user_id=user.id, job_type=JOB_TYPE_VOICE_TRAIN, input_path=str(input_path))
    consume_credits(db, user, config.voice_train_cost, "干声训练", job.id)
    db.commit()
    db.refresh(job)
    logger.info("Created voice_train job id=%s user_id=%s input=%s", job.id, user.id, input_path)
    return JobResponse.model_validate(job)


@router.post("/voice-train/complete", response_model=JobResponse)
def complete_voice_train_job(
    payload: UploadedObject,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    config = get_product_config(db)
    metadata = json.dumps(
        {
            "input": payload.model_dump(),
            "source": "oss",
        },
        ensure_ascii=True,
    )
    job = queue.create_job(
        db,
        user_id=user.id,
        job_type=JOB_TYPE_VOICE_TRAIN,
        input_path=payload.public_url,
        metadata_json=metadata,
    )
    consume_credits(db, user, config.voice_train_cost, "干声训练", job.id)
    db.commit()
    db.refresh(job)
    logger.info("Created OSS voice_train job id=%s user_id=%s input=%s", job.id, user.id, payload.public_url)
    return JobResponse.model_validate(job)


@router.post("/song-process", response_model=JobResponse)
async def create_song_process_job(
    task_name: str = Form(""),
    file: UploadFile = File(...),
    lyrics_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    config = get_product_config(db)
    input_path = await storage.save_upload(file, "song_process")
    lyrics_path = await storage.save_upload(lyrics_file, "song_lyrics")
    display_name = task_name.strip() or Path(input_path).stem
    metadata = json.dumps({"lyrics_path": str(lyrics_path), "task_name": display_name}, ensure_ascii=True)
    job = queue.create_job(
        db,
        user_id=user.id,
        job_type=JOB_TYPE_SONG_PROCESS,
        input_path=str(input_path),
        metadata_json=metadata,
    )
    consume_credits(db, user, config.song_process_cost, "歌曲处理", job.id)
    db.commit()
    db.refresh(job)
    logger.info(
        "Created song_process job id=%s user_id=%s name=%s input=%s lyrics=%s",
        job.id,
        user.id,
        display_name,
        input_path,
        lyrics_path,
    )
    return JobResponse.model_validate(job)


@router.post("/song-process/complete", response_model=JobResponse)
def complete_song_process_job(
    payload: SongUploadCompleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> JobResponse:
    config = get_product_config(db)
    display_name = payload.task_name.strip() or Path(payload.audio.filename or payload.audio.object_key).stem
    metadata = json.dumps(
        {
            "input": payload.audio.model_dump(),
            "lyrics": payload.lyrics.model_dump(),
            "lyrics_path": payload.lyrics.public_url,
            "task_name": display_name,
            "source": "oss",
        },
        ensure_ascii=True,
    )
    job = queue.create_job(
        db,
        user_id=user.id,
        job_type=JOB_TYPE_SONG_PROCESS,
        input_path=payload.audio.public_url,
        metadata_json=metadata,
    )
    consume_credits(db, user, config.song_process_cost, "歌曲处理", job.id)
    db.commit()
    db.refresh(job)
    logger.info(
        "Created OSS song_process job id=%s user_id=%s name=%s input=%s lyrics=%s",
        job.id,
        user.id,
        display_name,
        payload.audio.public_url,
        payload.lyrics.public_url,
    )
    return JobResponse.model_validate(job)


@router.get("", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[JobResponse]:
    return [JobResponse.model_validate(job) for job in queue.list_jobs(db, user_id=user.id)]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> JobResponse:
    job = queue.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Response:
    job = queue.get_job(db, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "running":
        raise HTTPException(status_code=409, detail="Running job cannot be deleted")
    db.execute(update(CreditTransaction).where(CreditTransaction.job_id == job.id).values(job_id=None))
    db.delete(job)
    db.commit()
    return Response(status_code=204)


@router.get("/{job_id}/download")
def download_job_output(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> FileResponse:
    job = queue.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JOB_STATUS_SUCCESS or not job.output_path:
        raise HTTPException(status_code=409, detail="Job output is not ready")
    if job.output_path.startswith(("http://", "https://")):
        return RedirectResponse(job.output_path)
    output = Path(job.output_path)
    if not output.exists() or not output.is_file():
        raise HTTPException(status_code=404, detail="Output file missing")
    return FileResponse(str(output), filename=output.name)


@router.get("/{job_id}/files/{file_kind}")
def download_job_file(
    job_id: int,
    file_kind: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> FileResponse:
    job = queue.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JOB_STATUS_SUCCESS:
        raise HTTPException(status_code=409, detail="Job output is not ready")
    if job.type != JOB_TYPE_SONG_PROCESS:
        raise HTTPException(status_code=400, detail="Job does not have song files")

    metadata_file_url = output_file_url(job.metadata_json, file_kind)
    if metadata_file_url:
        return RedirectResponse(metadata_file_url)

    output_dir = storage.song_output_dir(job.id)
    allowed = {
        "ai_vocal": output_dir / "ai_vocal.wav",
        "instrumental": output_dir / "instrumental.wav",
    }
    if file_kind == "lyrics":
        matches = sorted(output_dir.glob("lyrics.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="Lyrics file missing")
        target = matches[0]
    else:
        target = allowed.get(file_kind)
        if target is None:
            raise HTTPException(status_code=404, detail="Unknown song file")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Song file missing")
    return FileResponse(str(target), filename=target.name)


def output_file_url(metadata_json: str | None, file_kind: str) -> str | None:
    if not metadata_json:
        return None
    try:
        metadata = json.loads(metadata_json)
    except json.JSONDecodeError:
        return None
    output_files = metadata.get("output_files")
    if not isinstance(output_files, dict):
        return None
    item = output_files.get(file_kind)
    if isinstance(item, dict):
        url = item.get("public_url")
        return url if isinstance(url, str) and url else None
    return None
