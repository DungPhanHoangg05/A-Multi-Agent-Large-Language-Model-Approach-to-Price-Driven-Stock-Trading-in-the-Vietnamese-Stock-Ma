FROM python:3.13.5-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    MPLBACKEND=Agg \
    HF_HOME=/home/app/.cache/huggingface \
    VISOBERT_DEVICE=cpu \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Cài PyTorch bản CPU để tránh tải các thư viện CUDA không dùng trên VM.
RUN python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && python -m pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 app
COPY --chown=app:app . .
RUN mkdir -p backtest_result outputs /home/app/.cache/huggingface \
    && chown -R app:app /app /home/app/.cache
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=5)"
# Một worker giữ chung trạng thái tác vụ và chỉ nạp một bản mô hình ViSoBERT.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "300", "--graceful-timeout", "300", "--access-logfile", "-", "--error-logfile", "-", "web_interface:app"]
