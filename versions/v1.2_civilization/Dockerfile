# BTCU Harness Dockerfile
# Multi-stage build for smaller image

FROM python:3.12-slim as builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY btcu_harness/ btcu_harness/

RUN pip install --no-cache-dir build && python -m build --wheel

# ---- Runtime ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="BTCU Harness"
LABEL org.opencontainers.image.description="Balanced Ternary Cognitive Unit Harness"
LABEL org.opencontainers.image.source="https://github.com/q1z2q3-debug/btcu-harness"
LABEL org.opencontainers.image.license="MIT"

WORKDIR /app

# Install the wheel from builder
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl "fastapi>=0.100" "uvicorn[standard]>=0.20" && rm /tmp/*.whl

# Copy docs
COPY docs/ /app/docs/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "btcu_harness.api:app", "--host", "0.0.0.0", "--port", "8000"]
