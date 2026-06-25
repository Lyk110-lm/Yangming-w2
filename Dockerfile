FROM python:3.11-slim

WORKDIR /app

# 系统依赖(sqlite3 在 python:3.11-slim 里已有)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY api_requirements.txt .
RUN pip install --no-cache-dir -r api_requirements.txt

# 代码 + 数据
COPY api_consult.py .
COPY oral_to_concept.json .
COPY entries.db .

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# 启动
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api_consult:app --host 0.0.0.0 --port ${PORT}"]
