"""Báo cáo tiến độ (Phase 5).

- PM và Dept Leader tạo BẢN NHÁP; chỉ Dept Leader duyệt thành chính thức (PUBLISHED).
- Số liệu do code tính (cùng hàm với dashboard); Gemini chỉ diễn đạt nhận xét và bị kiểm tra từng con số.
- Nhân viên chỉ xem báo cáo chính thức của phòng ban mình. Admin không xem nội dung.
- Báo cáo là ảnh chụp tại lúc tạo: dữ liệu task đổi sau đó không làm đổi báo cáo đã lưu.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dashboard import compute_summary
from app.core.config import get_settings
from app.core.deps import audit, get_current_user, require_roles
from app.db.session import get_db
from app.models import Report, Role, User
from app.schemas.reports import ReportCreate, ReportListItem, ReportOut
from app.services.extraction.base import ExtractionError
from app.services.extraction.gemini import GeminiExtractor
from app.services.reporting.narrative import generate_narrative

router = APIRouter(tags=["reports"])
author = require_roles(Role.PM, Role.DEPT_LEADER)
approver = require_roles(Role.DEPT_LEADER)


def _visible(user: User):
    stmt = select(Report).where(Report.organization_id == user.organization_id)
    if user.role == Role.ADMIN or user.department_id is None:
        return stmt.where(Report.id.is_(None))  # không có gì
    stmt = stmt.where(Report.department_id == user.department_id)
    if user.role == Role.EMPLOYEE:
        stmt = stmt.where(Report.status == "PUBLISHED")
    return stmt


def _get(db: Session, user: User, report_id: uuid.UUID) -> Report:
    r = db.scalar(_visible(user).where(Report.id == report_id))
    if r is None:
        raise HTTPException(404, "Report not found")
    return r


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportCreate, db: Session = Depends(get_db), user: User = Depends(author)):
    writer = None
    if body.use_llm:
        s = get_settings()
        try:
            writer = GeminiExtractor(s.gemini_api_key, s.gemini_model).write_narrative
        except ExtractionError as e:
            raise HTTPException(422, str(e))
    kpis = compute_summary(db, user, body.as_of)
    result = generate_narrative(kpis, writer)
    rep = Report(
        organization_id=user.organization_id, department_id=user.department_id,
        title=(body.title or f"Báo cáo tiến độ {kpis['as_of']}").strip()[:300], as_of=kpis["as_of"],
        kpis=jsonable_encoder(kpis), narrative=result.narrative, narrative_method=result.method,
        narrative_notes=result.rejected, status="DRAFT", created_by=user.id,
    )
    db.add(rep)
    db.flush()
    audit(db, user, "report.create", "report", rep.id, {"method": result.method, "rejected": len(result.rejected)})
    db.commit()
    return rep


@router.get("/reports", response_model=list[ReportListItem])
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(_visible(user).order_by(Report.created_at.desc()).limit(100)).all()


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get(db, user, report_id)


@router.post("/reports/{report_id}/publish", response_model=ReportOut)
def publish_report(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(approver)):
    rep = _get(db, user, report_id)
    if rep.status != "DRAFT":
        raise HTTPException(409, "Báo cáo đã được duyệt.")
    rep.status, rep.published_by, rep.published_at = "PUBLISHED", user.id, datetime.now(timezone.utc)
    audit(db, user, "report.publish", "report", rep.id)
    db.commit()
    return rep


@router.delete("/reports/{report_id}", status_code=204)
def delete_draft(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(author)):
    rep = _get(db, user, report_id)
    if rep.status != "DRAFT":
        raise HTTPException(409, "Chỉ xóa được bản nháp.")
    if rep.created_by != user.id and user.role != Role.DEPT_LEADER:
        raise HTTPException(403, "Chỉ người tạo hoặc trưởng phòng được xóa bản nháp.")
    audit(db, user, "report.delete", "report", rep.id)
    db.delete(rep)
    db.commit()
