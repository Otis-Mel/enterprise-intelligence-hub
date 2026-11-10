FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Phase 1: tạo bảng khi khởi động qua Alembic (xem README); dev có thể dùng create_all
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
