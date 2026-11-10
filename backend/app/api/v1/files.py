"""Upload file + khởi chạy/theo dõi import (Phase 2)."""
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import permissions as perm
from app.core.config import get_settings
from app.core.deps import audit, get_current_user, require_roles
from app.core.storage import resolve_key, storage_root
from app.db import session as session_mod
from app.db.session import get_db
from app.models import ImportJob, ProcessingStatus, RawRecord, Role, UploadedFile, User
from app.schemas.ingestion import ImportJobOut, ImportListItem, ImportRequest, RawRecordOut, UploadedFileOut
from app.services.ingestion.service import run_import
from app.services.parsers import SUPPORTED_EXTENSIONS, sniff_matches_extension

router = APIRouter(tags=["ingestion"])
uploader = require_roles(Role.EMPLOYEE, Role.PM, Role.DEPT_LEADER)

CHUNK = 1024 * 1024


def _run_import_task(job_id: uuid.UUID) -> None:
    # session riêng cho tác vụ nền (session của request đã đóng)
    with session_mod.SessionLocal() as db:
        run_import(db, job_id)


@router.post("/files/upload", response_model=UploadedFileOut, status_code=201)
def upload_file(
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(uploader),
):
    display_name = Path(file.filename or "upload").name[:300]  # bỏ mọi thành phần thư mục
    ext = Path(display_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, f"Định dạng không được hỗ trợ. Chấp nhận: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    org_dir = storage_root() / str(user.organization_id)
    org_dir.mkdir(parents=True, exist_ok=True)
    key = f"{user.organization_id}/{uuid.uuid4().hex}{ext}"
    dest = resolve_key(key)

    sha, size = hashlib.sha256(), 0
    try:
        with open(dest, "wb") as out:
            while chunk := file.file.read(CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(413, f"File vượt quá {get_settings().max_upload_mb} MB")
                sha.update(chunk)
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "File rỗng")
        if not sniff_matches_extension(dest, ext):
            raise HTTPException(422, "Nội dung file không khớp với đuôi file")
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    checksum = sha.hexdigest()
    # Chỉ khử trùng trong CÙNG phòng ban (khác phòng ban không được biết file kia có tồn tại)
    dup = db.scalar(
        select(UploadedFile).where(
            UploadedFile.organization_id == user.organization_id,
            UploadedFile.department_id == user.department_id,
            UploadedFile.checksum == checksum,
        )
    )
    if dup is not None:
        dest.unlink(missing_ok=True)
        response.status_code = 200
        return UploadedFileOut.model_validate(dup).model_copy(update={"duplicate": True})

    f = UploadedFile(
        organization_id=user.organization_id,
        department_id=user.department_id,
        file_name=display_name,
        file_type=ext,
        storage_key=key,
        size_bytes=size,
        checksum=checksum,
        uploaded_by=user.id,
    )
    db.add(f)
    db.flush()
    audit(db, user, "file.upload", "uploaded_file", f.id, {"name": display_name, "size": size})
    db.commit()
    return f


@router.get("/files", response_model=list[UploadedFileOut])
def list_files(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(perm.visible_files_stmt(user).order_by(UploadedFile.uploaded_at.desc())).all()


@router.post("/imports", response_model=ImportJobOut, status_code=202)
def start_import(
    body: ImportRequest,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(uploader),
):
    f = db.scalar(perm.visible_files_stmt(user).where(UploadedFile.id == body.file_id))
    if f is None:
        raise HTTPException(404, "File not found")

    # Idempotent: đã có job không-thất-bại cho file này thì trả lại job đó
    existing = db.scalar(
        select(ImportJob)
        .where(ImportJob.uploaded_file_id == f.id, ImportJob.status != ProcessingStatus.FAILED)
        .order_by(ImportJob.created_at.desc())
    )
    if existing is not None:
        response.status_code = 200
        return existing

    job = ImportJob(organization_id=user.organization_id, uploaded_file_id=f.id, requested_by=user.id)
    db.add(job)
    db.flush()
    audit(db, user, "import.start", "import_job", job.id, {"file_id": str(f.id)})
    db.commit()
    background.add_task(_run_import_task, job.id)
    return job


@router.get("/imports", response_model=list[ImportListItem])
def list_imports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    files = {f.id: f for f in db.scalars(perm.visible_files_stmt(user)).all()}
    if not files:
        return []
    jobs = db.scalars(select(ImportJob).where(ImportJob.uploaded_file_id.in_(list(files))).order_by(ImportJob.created_at.desc())).all()
    return [
        ImportListItem(
            job_id=j.id, file_id=j.uploaded_file_id, file_name=files[j.uploaded_file_id].file_name, status=j.status,
            created_at=j.created_at, records_read=j.records_read, records_created=j.records_created, error_summary=j.error_summary,
        )
        for j in jobs
    ]


def _visible_job(db: Session, user: User, job_id: uuid.UUID) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or db.scalar(perm.visible_files_stmt(user).where(UploadedFile.id == job.uploaded_file_id)) is None:
        raise HTTPException(404, "Import job not found")
    return job


@router.get("/imports/{job_id}", response_model=ImportJobOut)
def get_import(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _visible_job(db, user, job_id)


@router.get("/imports/{job_id}/raw", response_model=list[RawRecordOut])
def preview_raw(
    job_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _visible_job(db, user, job_id)
    return db.scalars(
        select(RawRecord)
        .where(RawRecord.uploaded_file_id == job.uploaded_file_id)
        .order_by(RawRecord.imported_at, RawRecord.row_ref)
        .limit(limit)
        .offset(offset)
    ).all()
