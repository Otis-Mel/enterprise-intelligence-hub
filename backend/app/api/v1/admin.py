"""Quản trị: người dùng & phòng ban (chỉ ADMIN)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import audit, get_current_user, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Department, Role, User
from app.schemas import DepartmentCreate, DepartmentOut, UserCreate, UserOut
from app.schemas.dashboard import DirectoryUser

router = APIRouter(tags=["admin"])
admin_only = require_roles(Role.ADMIN)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown department")
    user = User(
        organization_id=admin.organization_id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        department_id=body.department_id,
    )
    db.add(user)
    db.flush()
    audit(db, admin, "user.create", "user", user.id, {"role": body.role.value})
    db.commit()
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    return db.scalars(select(User).where(User.organization_id == admin.organization_id)).all()


@router.patch("/users/{user_id}/active", response_model=UserOut)
def set_active(user_id: uuid.UUID, active: bool, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user or user.organization_id != admin.organization_id:
        raise HTTPException(404, "User not found")
    user.is_active = active
    audit(db, admin, "user.set_active", "user", user.id, {"active": active})
    db.commit()
    return user


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    dept = Department(organization_id=admin.organization_id, **body.model_dump())
    db.add(dept)
    db.flush()
    audit(db, admin, "department.create", "department", dept.id, {"name": dept.name})
    db.commit()
    return dept


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Department).where(Department.organization_id == user.organization_id)
    # Không-admin chỉ thấy phòng ban của mình
    if user.role != Role.ADMIN:
        stmt = stmt.where(Department.id == user.department_id)
    return db.scalars(stmt).all()


@router.get("/directory", response_model=list[DirectoryUser])
def directory(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Danh sách tên người dùng đang hoạt động CÙNG PHÒNG BAN (chỉ id + tên, không có email) để chọn người phụ trách."""
    if user.role == Role.ADMIN or user.department_id is None:
        return []
    stmt = select(User).where(
        User.organization_id == user.organization_id, User.department_id == user.department_id, User.is_active.is_(True)
    ).order_by(User.full_name)
    return db.scalars(stmt).all()
