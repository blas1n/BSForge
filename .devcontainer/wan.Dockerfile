# Wan 2.2 Video Generation Service Dockerfile
# Runs Wan 2.2 T2V as a standalone API service

FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libglib2.0-dev \
    ffmpeg \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# diffusers >= 0.32 for WanPipeline support
RUN pip install --no-cache-dir \
    "torch>=2.3.0" \
    "diffusers>=0.32.0" \
    "transformers>=4.40.0,<5.0.0" \
    "accelerate>=0.27.0" \
    "safetensors>=0.4.0" \
    "fastapi>=0.109.0" \
    "uvicorn>=0.27.0" \
    "pillow>=10.0.0" \
    "opencv-python-headless>=4.9.0" \
    "imageio[ffmpeg]>=2.34.0"

# Copy Wan server
COPY services/wan/wan_server.py /app/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -f http://localhost:7861/health || exit 1

EXPOSE 7861

# Run with uvicorn
CMD ["uvicorn", "wan_server:app", "--host", "0.0.0.0", "--port", "7861"]
