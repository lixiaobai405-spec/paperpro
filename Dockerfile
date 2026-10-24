FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/src ./src
COPY frontend/public ./public
COPY frontend/index.html frontend/vite.config.js ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.17 AS uv
FROM python:3.12-slim-trixie AS python-build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --python /usr/local/bin/python

FROM python:3.12-slim-trixie AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice-writer fonts-noto-cjk fonts-wqy-zenhei fonts-dejavu-core \
       fontconfig libgl1 libglib2.0-0t64 libgomp1 tesseract-ocr \
    && fc-cache -f \
    && grep -q 'DisableMacrosExecution' /usr/lib/libreoffice/share/registry/main.xcd \
    && grep -q 'DisableActiveContent' /usr/lib/libreoffice/share/registry/main.xcd \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 HOME=/tmp \
    PAPERPRO_OCR_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    PAPERPRO_PDF_ENGINE=libreoffice \
    PAPERPRO_RESUME_FONT="Noto Sans CJK SC"
COPY --from=python-build /app/.venv /app/.venv
COPY app ./app
COPY settings.json ./settings.json
COPY scripts/smoke_linux_documents.py ./scripts/smoke_linux_documents.py
COPY --from=frontend-build /build/frontend/dist ./frontend/dist
# Refuse a mistakenly edited public credential template, without echoing it.
RUN python -c "import json; d=json.load(open('settings.json')); assert not any(d.get(k, {}).get('api_key') for k in ('deepseek','configured')), 'settings.json must not contain credentials'"
# Root administers Docker on the host. Use the image's existing nobody identity
# for the app/converter; no server account or privileged container is needed.
USER 65534:65534
EXPOSE 8766
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8766/api/health',timeout=3); assert r.status==200"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8766", "--workers", "1"]
