FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .

ENV PINGPONG_MODE=mock \
    PINGPONG_WEBHOOK_SECRET=local-demo-secret \
    DATABASE_URL=sqlite:///./pingpong.db

EXPOSE 8000
CMD ["sh", "-c", "python scripts/migrate.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
