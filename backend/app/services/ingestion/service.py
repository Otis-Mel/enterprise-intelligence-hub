"""Chạy một import job: parse file -> lưu raw_records (idempotent theo (file, row_ref))."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import audit
from app.core.storage import resolve_key
from app.models import ImportJob, ProcessingStatus, RawRecord, UploadedFile, User
from app.services.parsers import parse_file
from app.services.parsers.base import ParseError

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(db: Session, job_id: uuid.UUID, message: str) -> None:
    db.rollback()
    job = db.get(ImportJob, job_id)
    f = db.get(UploadedFile, job.uploaded_file_id)
    job.status = f.processing_status = ProcessingStatus.FAILED
    job.error_summary = message[:1000]
    job.finished_at = _now()
    audit(db, db.get(User, job.requested_by), "import.failed", "import_job", job.id, {"error": message[:300]})
    db.commit()


def run_import(db: Session, job_id: uuid.UUID) -> None:
    job = db.get(ImportJob, job_id)
    if job is None:
        return
    f = db.get(UploadedFile, job.uploaded_file_id)
    job.status = f.processing_status = ProcessingStatus.PARSING
    job.started_at = _now()
    db.commit()

    try:
        doc = parse_file(resolve_key(f.storage_key), f.file_type)

        existing = set(db.scalars(select(RawRecord.row_ref).where(RawRecord.uploaded_file_id == f.id)))
        created = skipped = 0
        for rec in doc.records:
            if rec.row_ref in existing:  # chạy lại không tạo bản ghi trùng
                skipped += 1
                continue
            db.add(
                RawRecord(
                    organization_id=f.organization_id,
                    uploaded_file_id=f.id,
                    import_job_id=job.id,
                    row_ref=rec.row_ref,
                    kind=rec.kind,
                    payload=rec.payload,
                )
            )
            existing.add(rec.row_ref)
            created += 1

        job.records_read, job.records_created, job.records_skipped = len(doc.records), created, skipped
        job.warnings = doc.warnings
        # PDF scan: cần OCR/xem lại trước khi map; còn lại sang bước map/chuẩn hóa (Phase 3)
        final = ProcessingStatus.NEEDS_REVIEW if doc.needs_ocr else ProcessingStatus.NEEDS_MAPPING
        job.status = f.processing_status = final
        job.finished_at = _now()
        audit(db, db.get(User, job.requested_by), "import.parsed", "import_job", job.id,
              {"file": f.file_name, "read": len(doc.records), "created": created})
        db.commit()
    except ParseError as e:
        _fail(db, job_id, str(e))
    except Exception:  # lỗi không lường trước: log chi tiết phía server, chỉ trả thông điệp chung cho người dùng
        log.exception("import job %s failed", job_id)
        _fail(db, job_id, "Lỗi không mong muốn khi xử lý file. Vui lòng thử lại hoặc liên hệ quản trị viên.")
