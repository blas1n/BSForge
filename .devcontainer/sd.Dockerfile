# Stable Diffusion Service Dockerfile
# Runs SDXL Turbo as a standalone API service

FROM python:3.11-slim

# System dependencies for image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    torch \
    diffusers>=0.26.0 \
    transformers>=4.38.0 \
    accelerate>=0.27.0 \
    safetensors>=0.4.0 \
    fastapi>=0.109.0 \
    uvicorn>=0.27.0 \
    httpx>=0.26.0 \
    pillow>=10.0.0

# Copy SD server
COPY services/sd/sd_server.py /app/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

EXPOSE 7860

# Run with uvicorn
CMD ["uvicorn", "sd_server:app", "--host", "0.0.0.0", "--port", "7860"]
