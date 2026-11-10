"""Enum dùng chung. Đặt ngoài app.models để logic thuần (chuẩn hóa, đánh giá) import được mà không cần SQLAlchemy."""
import enum


class Role(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    PM = "PM"
    DEPT_LEADER = "DEPT_LEADER"
    ADMIN = "ADMIN"


class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class Priority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ProcessingStatus(str, enum.Enum):
    """Mục 4.1 của plan."""

    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    NEEDS_MAPPING = "NEEDS_MAPPING"  # parse xong, raw đã lưu, chờ chuẩn hóa
    NEEDS_REVIEW = "NEEDS_REVIEW"  # có bản ghi cần người xem
    VALIDATED = "VALIDATED"  # đã chuẩn hóa, không còn bản ghi chờ xử lý đặc biệt
    APPROVED = "APPROVED"
    IMPORTED = "IMPORTED"
    FAILED = "FAILED"


class ProjectStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ReviewStatus(str, enum.Enum):
    """Trạng thái từng bản ghi đã chuẩn hóa trong hàng chờ duyệt."""

    PENDING = "PENDING"  # có cảnh báo/lỗi, cần người xem
    CLEAN = "CLEAN"  # không có vấn đề, chờ người duyệt hàng loạt
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IMPORTED = "IMPORTED"  # đã đưa vào bảng tasks
