"""Phase 3: chuẩn hóa -> hàng chờ duyệt -> commit vào tasks.

Phân quyền:
- Chạy chuẩn hóa / xem hàng chờ: người dùng thấy được file (xem core/permissions.visible_files_stmt).
- Sửa, duyệt, từ chối, commit: chỉ PM và Dept Leader (người chịu trách nhiệm dữ liệu của phòng ban).
- Dữ liệu chỉ vào bảng tasks sau khi được duyệt (human-in-the-loop); LLM chỉ gợi ý, không tự ghi dữ liệu chính thức.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.files import _visible_job, uploader
from app.core import permissions as perm
from app.core.deps import audit, get_current_user, require_roles
from app.db.session import get_db
from app.models import ImportJob, NormalizedRecord, ProcessingStatus, Project, ReviewStatus, Role, UploadedFile, User
from app.schemas.review import (
    ApproveCleanResult,
    CommitRequest,
    CommitResult,
    NormalizedRecordOut,
    NormalizedRecordPatch,
    NormalizeRequest,
    NormalizeSummary,
)
from app.services.extraction.base import ExtractionError
from app.services.ingestion.normalize import (
    _natural_key,
    classify,
    commit_records,
    has_error,
    issues_for,
    refresh_file_status,
    run_normalization,
    summarize,
)
from app.services.mapping.normalizers import clean_text

router = APIRouter(tags=["review"])
manager = require_roles(Role.PM, Role.DEPT_LEADER)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _visible_record(db: Session, user: User, record_id: uuid.UUID) -> NormalizedRecord:
    rec = db.get(NormalizedRecord, record_id)
    if rec is None or db.scalar(perm.visible_files_stmt(user).where(UploadedFile.id == rec.uploaded_file_id)) is None:
        raise HTTPException(404, "Record not found")
    return rec


@router.post("/imports/{job_id}/normalize", response_model=NormalizeSummary)
def normalize(job_id: uuid.UUID, body: NormalizeRequest, db: Session = Depends(get_db), user: User = Depends(uploader)):
    job = _visible_job(db, user, job_id)
    if job.status in (ProcessingStatus.UPLOADED, ProcessingStatus.PARSING, ProcessingStatus.FAILED):
        raise HTTPException(409, "File chưa được đọc xong hoặc đọc thất bại; chưa thể chuẩn hóa.")
    try:
        return run_normalization(
            db, job, user, column_mapping=body.column_mapping, date_order=body.date_order, use_llm=body.use_llm, force=body.force
        )
    except ExtractionError as e:
        db.rollback()
        code = 422 if "GEMINI_API_KEY" in str(e) else 502
        raise HTTPException(code, str(e))


@router.get("/imports/{job_id}/summary", response_model=NormalizeSummary)
def get_summary(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _visible_job(db, user, job_id)
    return summarize(db, job, db.get(UploadedFile, job.uploaded_file_id))


@router.get("/imports/{job_id}/records", response_model=list[NormalizedRecordOut])
def list_records(
    job_id: uuid.UUID,
    review_status: ReviewStatus | None = None,
    only_issues: bool = False,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _visible_job(db, user, job_id)
    stmt = select(NormalizedRecord).where(NormalizedRecord.uploaded_file_id == job.uploaded_file_id)
    if review_status:
        stmt = stmt.where(NormalizedRecord.review_status == review_status)
    rows = sorted(db.scalars(stmt).all(), key=lambda r: _natural_key(r.row_ref))  # thứ tự như trong file
    if only_issues:
        rows = [r for r in rows if r.issues]
    return rows[offset : offset + limit]


@router.patch("/normalized-records/{record_id}", response_model=NormalizedRecordOut)
def patch_record(record_id: uuid.UUID, body: NormalizedRecordPatch, db: Session = Depends(get_db), user: User = Depends(manager)):
    rec = _visible_record(db, user, record_id)
    if rec.review_status == ReviewStatus.IMPORTED:
        raise HTTPException(409, "Bản ghi đã được đưa vào tasks, không thể sửa ở đây.")

    data = body.model_dump(exclude_unset=True)
    decision = data.pop("decision", None)
    if data.get("status_normalized", 0) is None or data.get("priority_normalized", 0) is None:
        raise HTTPException(422, "status_normalized/priority_normalized không được null.")

    flags = dict(rec.field_flags or {})
    changed: list[str] = []
    if "title" in data:
        rec.title = clean_text(data["title"])
        changed.append("title")
    if "assignee_id" in data:
        uid = data["assignee_id"]
        if uid is not None:
            u = db.get(User, uid)
            f = db.get(UploadedFile, rec.uploaded_file_id)
            if not u or not u.is_active or u.organization_id != rec.organization_id or u.department_id != f.department_id:
                raise HTTPException(422, "Người phụ trách phải là người dùng đang hoạt động trong cùng phòng ban.")
            rec.assignee_raw = rec.assignee_raw or u.full_name
        rec.assignee_id = uid
        changed.append("assignee_id")
    if "status_normalized" in data:
        rec.status_normalized = data["status_normalized"]
        changed.append("status_normalized")
    if "priority_normalized" in data:
        rec.priority_normalized = data["priority_normalized"]
        changed.append("priority_normalized")
    if "progress" in data:
        rec.progress = data["progress"]
        flags.pop("progress", None)  # người đã quyết -> hết mơ hồ
        changed.append("progress")
    if "due_date" in data:
        rec.due_date = data["due_date"]
        flags.pop("due_date", None)
        changed.append("due_date")
    if changed:
        rec.edited = True
        rec.field_flags = flags

    issues = issues_for(rec)
    rec.issues = issues

    if decision == "APPROVE":
        if has_error(issues):
            raise HTTPException(422, {"message": "Còn lỗi bắt buộc phải sửa trước khi duyệt.", "issues": [i for i in issues if i["severity"] == "error"]})
        rec.review_status, rec.reviewed_by, rec.reviewed_at = ReviewStatus.APPROVED, user.id, _now()
    elif decision == "REJECT":
        rec.review_status, rec.reviewed_by, rec.reviewed_at = ReviewStatus.REJECTED, user.id, _now()
    elif decision == "REOPEN":
        rec.review_status, rec.reviewed_by, rec.reviewed_at = classify(issues), None, None
    elif rec.review_status == ReviewStatus.APPROVED and has_error(issues):
        rec.review_status = ReviewStatus.PENDING  # sửa làm phát sinh lỗi -> rút lại phê duyệt
    elif rec.review_status in (ReviewStatus.PENDING, ReviewStatus.CLEAN):
        rec.review_status = classify(issues)

    audit(db, user, "record.review", "normalized_record", rec.id, {"changed": changed, "decision": decision})
    refresh_file_status(db, db.get(UploadedFile, rec.uploaded_file_id))
    db.commit()
    return rec


@router.post("/imports/{job_id}/approve-clean", response_model=ApproveCleanResult)
def approve_clean(job_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(manager)):
    """Duyệt hàng loạt các bản ghi KHÔNG có bất kỳ cảnh báo nào. Bản ghi có cảnh báo luôn cần người xem."""
    job = _visible_job(db, user, job_id)
    res = db.execute(
        update(NormalizedRecord)
        .where(NormalizedRecord.uploaded_file_id == job.uploaded_file_id, NormalizedRecord.review_status == ReviewStatus.CLEAN)
        .values(review_status=ReviewStatus.APPROVED, reviewed_by=user.id, reviewed_at=_now())
    )
    audit(db, user, "record.approve_clean", "import_job", job.id, {"approved": res.rowcount})
    db.flush()
    refresh_file_status(db, db.get(UploadedFile, job.uploaded_file_id), job)
    db.commit()
    return ApproveCleanResult(approved=res.rowcount)


@router.post("/imports/{job_id}/commit", response_model=CommitResult)
def commit(job_id: uuid.UUID, body: CommitRequest, db: Session = Depends(get_db), user: User = Depends(manager)):
    job: ImportJob = _visible_job(db, user, job_id)
    f = db.get(UploadedFile, job.uploaded_file_id)
    project = db.get(Project, body.project_id)
    if project is None or not perm.can_manage_project(user, project):
        raise HTTPException(403, "Bạn không có quyền trên project này.")
    if project.department_id != f.department_id:
        raise HTTPException(422, "Project thuộc phòng ban khác với file.")
    approved = db.scalar(
        select(NormalizedRecord.id).where(NormalizedRecord.uploaded_file_id == f.id, NormalizedRecord.review_status == ReviewStatus.APPROVED).limit(1)
    )
    if approved is None:
        raise HTTPException(409, "Chưa có bản ghi nào được duyệt.")
    return commit_records(db, job, user, project)
