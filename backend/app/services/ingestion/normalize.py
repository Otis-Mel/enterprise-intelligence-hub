"""Lớp DB của Phase 3: raw_records -> normalized_records (hàng chờ duyệt) -> tasks (sau khi người duyệt)."""
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import audit
from app.models import (
    ImportJob,
    NormalizedRecord,
    ProcessingStatus,
    RawRecord,
    ReviewStatus,
    Task,
    TaskUpdate,
    UploadedFile,
    User,
)
from app.services.extraction.base import ExtractionError, Extractor
from app.services.extraction.gemini import GeminiExtractor
from app.services.extraction.pattern import PatternExtractor
from app.services.mapping.pipeline import normalize_items
from app.services.validation.rules import has_error, validate_fields


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _natural_key(row_ref: str):
    """'S!R10' phải đứng sau 'S!R9' (sắp xếp tự nhiên) để 'dòng trùng = dòng xuất hiện sau' đúng thứ tự trong file."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", row_ref)]


def name_key(name: str | None) -> str:
    return " ".join(unicodedata.normalize("NFC", name or "").casefold().split())


def get_extractor(use_llm: bool) -> Extractor:
    s = get_settings()
    if use_llm:
        return GeminiExtractor(s.gemini_api_key, s.gemini_model)  # ném ExtractionError nếu thiếu key
    return PatternExtractor()


def issues_for(rec: NormalizedRecord, check_assignee: bool = True) -> list[dict]:
    return validate_fields(
        title=rec.title, assignee_raw=rec.assignee_raw, assignee_id=rec.assignee_id, check_assignee=check_assignee,
        status=rec.status_normalized, priority=rec.priority_normalized, progress=None if rec.progress is None else float(rec.progress),
        due_date=rec.due_date, raw=rec.raw or {}, flags=rec.field_flags or {}, is_duplicate=rec.duplicate_of_id is not None,
    )


def classify(issues: list[dict]) -> ReviewStatus:
    return ReviewStatus.PENDING if issues else ReviewStatus.CLEAN


def refresh_file_status(db: Session, f: UploadedFile, job: ImportJob | None = None) -> None:
    """Trạng thái file suy ra từ các bản ghi: còn bản ghi chờ -> NEEDS_REVIEW; không còn -> VALIDATED/APPROVED/IMPORTED."""
    db.flush()  # session tắt autoflush: phải đẩy thay đổi chưa ghi xuống DB trước khi đếm
    counts = dict(db.execute(
        select(NormalizedRecord.review_status, func.count()).where(NormalizedRecord.uploaded_file_id == f.id).group_by(NormalizedRecord.review_status)
    ).all())
    waiting =counts.get(ReviewStatus.PENDING, 0) + counts.get(ReviewStatus.CLEAN, 0)
    if waiting:
        new = ProcessingStatus.NEEDS_REVIEW
    elif counts.get(ReviewStatus.APPROVED, 0):
        new = ProcessingStatus.APPROVED
    elif counts.get(ReviewStatus.IMPORTED, 0):
        new = ProcessingStatus.IMPORTED
    else:
        new = ProcessingStatus.VALIDATED
    f.processing_status = new
    if job is not None:
        job.status = new


def run_normalization(
    db: Session, job: ImportJob, user: User, *, column_mapping: dict[str, str], date_order: str | None, use_llm: bool, force: bool
) -> dict:
    f = db.get(UploadedFile, job.uploaded_file_id)
    existing = db.scalar(select(func.count()).select_from(NormalizedRecord).where(NormalizedRecord.uploaded_file_id == f.id))
    if existing and not force:
        return summarize(db, job, f, note="Đã chuẩn hóa trước đó; dùng force=true để chạy lại (không ghi đè bản ghi đã được người sửa/duyệt).")

    raws = sorted(db.scalars(select(RawRecord).where(RawRecord.uploaded_file_id == f.id)).all(), key=lambda r: _natural_key(r.row_ref))
    raw_by_ref = {r.row_ref: r for r in raws}
    result = normalize_items(raws, extractor=get_extractor(use_llm), column_overrides=column_mapping, date_order=date_order)

    # chạy lại (force): xóa bản ghi chưa ai đụng tới, giữ bản đã sửa/duyệt
    if existing:
        db.execute(delete(NormalizedRecord).where(
            NormalizedRecord.uploaded_file_id == f.id,
            NormalizedRecord.edited.is_(False),
            NormalizedRecord.review_status.in_([ReviewStatus.PENDING, ReviewStatus.CLEAN]),
        ))
        db.flush()
    kept_refs = set(db.scalars(select(NormalizedRecord.row_ref).where(NormalizedRecord.uploaded_file_id == f.id)))

    # tên người dùng trong phòng ban; tên trùng nhau (2 người cùng tên) -> không khớp, để người duyệt chọn
    by_name: dict[str, list[uuid.UUID]] = {}
    for u in db.scalars(select(User).where(User.organization_id == f.organization_id, User.department_id == f.department_id, User.is_active.is_(True))):
        by_name.setdefault(name_key(u.full_name), []).append(u.id)

    id_by_ref: dict[str, uuid.UUID] = {}
    created: list[tuple[NormalizedRecord, str | None]] = []
    for it in result.items:
        if it.row_ref in kept_refs:
            continue
        raw = raw_by_ref.get(re.sub(r"#\d+$", "", it.row_ref)) or raw_by_ref.get(it.row_ref)  # 'page1#2' -> 'page1'
        if raw is None:
            continue
        match = by_name.get(name_key(it.assignee_raw), []) if it.assignee_raw else []
        rec = NormalizedRecord(
            organization_id=f.organization_id, department_id=f.department_id, uploaded_file_id=f.id, raw_record_id=raw.id,
            row_ref=it.row_ref, extraction_method=it.extraction_method, evidence=it.evidence, external_id=it.external_id,
            title=it.title, assignee_raw=it.assignee_raw, assignee_id=match[0] if len(match) == 1 else None,
            status_normalized=it.status, priority_normalized=it.priority, progress=it.progress, due_date=it.due_date,
            raw=it.raw, field_flags=it.flags,
        )
        db.add(rec)
        created.append((rec, it.duplicate_of))
    db.flush()
    id_by_ref.update({r.row_ref: r.id for r in db.scalars(select(NormalizedRecord).where(NormalizedRecord.uploaded_file_id == f.id))})
    for rec, dup_ref in created:
        rec.duplicate_of_id = id_by_ref.get(dup_ref) if dup_ref else None
        rec.issues = issues_for(rec)
        rec.review_status = classify(rec.issues)

    job.normalize_config = {"column_mapping": column_mapping, "date_order": date_order, "use_llm": use_llm,
                            "detected_date_orders": result.date_orders, "column_mappings": result.column_mappings}
    job.warnings = list(job.warnings or []) + result.warnings
    refresh_file_status(db, f, job)
    audit(db, user, "normalize.run", "import_job", job.id, {"records": len(created), "extractor": "gemini" if use_llm else "pattern"})
    db.commit()

    suggestions: dict[str, str] = {}
    unmapped = {s: h for s, h in result.unmapped_headers.items() if h}
    if unmapped and use_llm:
        try:
            ext = get_extractor(True)
            for sheet, headers in unmapped.items():
                sample = [r.payload for r in raws if r.kind == "row" and (r.row_ref.rsplit("!", 1)[0] if "!" in r.row_ref else "") == sheet][:3]
                suggestions.update(ext.suggest_column_mapping(headers, sample))
        except ExtractionError:
            pass  # gợi ý là tùy chọn
    return summarize(db, job, f, unmapped=unmapped, suggested_mapping=suggestions, warnings=result.warnings)


def summarize(db: Session, job: ImportJob, f: UploadedFile, **extra) -> dict:
    counts = dict(db.execute(
        select(NormalizedRecord.review_status, func.count()).where(NormalizedRecord.uploaded_file_id == f.id).group_by(NormalizedRecord.review_status)
    ).all())
    issue_counts: dict[str, int] = {}
    for issues in db.scalars(select(NormalizedRecord.issues).where(NormalizedRecord.uploaded_file_id == f.id)):
        for i in issues or []:
            issue_counts[i["code"]] = issue_counts.get(i["code"], 0) + 1
    return {
        "job_id": job.id,
        "file_status": f.processing_status,
        "total": sum(counts.values()),
        "by_review_status": {k.value: v for k, v in counts.items()},
        "issue_counts": issue_counts,
        "detected_date_orders": (job.normalize_config or {}).get("detected_date_orders", {}),
        "unmapped_headers": extra.get("unmapped", {}),
        "suggested_mapping": extra.get("suggested_mapping", {}),
        "warnings": extra.get("warnings", []),
        "note": extra.get("note"),
    }


def commit_records(db: Session, job: ImportJob, user: User, project) -> dict:
    """Đưa các bản ghi APPROVED vào bảng tasks. Idempotent theo (organization, source_system, external_id)."""
    f = db.get(UploadedFile, job.uploaded_file_id)
    source = f"file:{f.department_id}:{f.file_name}"[:100]
    recs = db.scalars(
        select(NormalizedRecord).where(NormalizedRecord.uploaded_file_id == f.id, NormalizedRecord.review_status == ReviewStatus.APPROVED)
        .order_by(NormalizedRecord.created_at)
    ).all()
    recs.sort(key=lambda r: _natural_key(r.row_ref))

    created = updated = unchanged = 0
    for rec in recs:
        ext_id = (rec.external_id or rec.row_ref)[:200]
        values = dict(
            title=rec.title, assignee_id=rec.assignee_id, assignee_name_raw=rec.assignee_raw,
            status_original=(rec.raw or {}).get("status"), status_normalized=rec.status_normalized,
            priority_original=(rec.raw or {}).get("priority"), priority_normalized=rec.priority_normalized,
            progress=rec.progress, due_date=rec.due_date,
        )
        task = db.scalar(select(Task).where(Task.organization_id == f.organization_id, Task.source_system == source, Task.external_id == ext_id))
        if task is None:
            db.add(Task(
                organization_id=f.organization_id, department_id=project.department_id, project_id=project.id,
                source_system=source, external_id=ext_id, last_synced_at=_now(), **values,
            ))
            db.flush()  # autoflush tắt: nếu hai bản ghi cùng mã, bản sau phải thấy task vừa tạo để cập nhật thay vì tạo trùng
            created += 1
        else:
            old, new = {}, {}
            for k, v in values.items():
                cur = getattr(task, k)
                if (None if cur is None else str(getattr(cur, "value", cur))) != (None if v is None else str(getattr(v, "value", v))):
                    old[k], new[k] = (None if cur is None else str(getattr(cur, "value", cur))), (None if v is None else str(getattr(v, "value", v)))
                    setattr(task, k, v)
            task.last_synced_at = _now()
            if new:
                db.add(TaskUpdate(task_id=task.id, updated_by=user.id, old_values=old, new_values=new, comment=f"Cập nhật từ file {f.file_name}"))
                updated += 1
            else:
                unchanged += 1
        rec.review_status = ReviewStatus.IMPORTED
        rec.reviewed_by = rec.reviewed_by or user.id
    db.flush()
    refresh_file_status(db, f, job)
    audit(db, user, "import.commit", "import_job", job.id, {"created": created, "updated": updated, "unchanged": unchanged, "project_id": str(project.id)})
    db.commit()
    return {"created": created, "updated": updated, "unchanged": unchanged, "file_status": f.processing_status}


__all__ = ["run_normalization", "commit_records", "summarize", "issues_for", "classify", "refresh_file_status", "has_error", "name_key"]
