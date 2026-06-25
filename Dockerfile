FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY api_requirements.txt .
RUN pip install --no-cache-dir -r api_requirements.txt

# 代码 + 数据
COPY api_consult.py .
COPY query_index.py .
COPY rag_query.py .
COPY search_concepts.py .
COPY oral_to_concept.json .
COPY entries.db .

# 端口(Railway 会注入 $PORT,默认 8000 兜底)
ENV PORT=8000
EXPOSE 8000

# shell 形式,让 sh 解析 $PORT
CMD uvicorn api_consult:app --host 0.0.0.0 --port ${PORT:-8000}
