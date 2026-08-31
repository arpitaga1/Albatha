FROM python:3.12-slim

# Tesseract OCR (real_extraction.py's invoice/box-label OCR path) and
# OpenCV's runtime shared libraries (libGL/libglib) are OS packages, not
# pip packages - neither is present on a plain Python buildpack, which is
# exactly why this needs a Docker-based deploy rather than Render's (or
# any platform's) default Python runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render (and most PaaS hosts) inject $PORT at runtime; default to 8000 so
# `docker run -p 8000:8000 ...` still works for local testing.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
