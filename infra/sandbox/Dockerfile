# Sandbox image for the analyst agent's run_python tool.
# Run with: --network none --read-only --memory 512m (see backend.analyst.sandbox).
FROM python:3.11-slim

RUN pip install --no-cache-dir "pandas>=2.2,<3" "numpy>=1.26,<3" "scipy>=1.11,<2"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp

WORKDIR /out
