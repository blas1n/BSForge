"""Stable Diffusion API Server.

Runs as a standalone service in a Docker container.
Provides HTTP API for image generation using SDXL Turbo.

Usage:
    uvicorn sd_server:app --host 0.0.0.0 --port 7860
"""

import base64
import io
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import torch
from diffusers import AutoPipelineForText2Image
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global pipeline instance (lazy loaded)
_pipeline: Any = None
_device: str = "cpu"


def _detect_device() -> str:
    """Detect best available device for inference.

    Returns:
        Device string: 'cuda', 'mps', or 'cpu'
    """
    # Check environment override
    env_device = os.environ.get("SD_DEVICE", "auto")
    if env_device != "auto":
        return env_device

    # Auto-detect
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_pipeline() -> Any:
    """Load SDXL Turbo pipeline.

    Returns:
        Loaded diffusion pipeline
    """
    global _device
    _device = _detect_device()

    logger.info(f"Loading SDXL Turbo on device: {_device}")

    # Determine torch dtype based on device
    torch_dtype = torch.float16 if _device in ("cuda", "mps") else torch.float32

    pipeline = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo",
        torch_dtype=torch_dtype,
        variant="fp16" if torch_dtype == torch.float16 else None,
    )

    pipeline = pipeline.to(_device)

    # Enable memory optimizations
    if _device == "cuda":
        pipeline.enable_model_cpu_offload()
    elif _device == "mps":
        # MPS doesn't support attention slicing well
        pass
    else:
        # CPU mode - enable sequential offload for memory
        pipeline.enable_sequential_cpu_offload()

    logger.info(f"SDXL Turbo loaded successfully on {_device}")
    return pipeline


def _image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64 string.

    Args:
        image: PIL Image

    Returns:
        Base64 encoded PNG string
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Pre-loads the model on startup for faster first inference.
    """
    global _pipeline
    logger.info("Starting SD server, pre-loading model...")

    try:
        _pipeline = _load_pipeline()
        logger.info("Model pre-loaded successfully")
    except Exception as e:
        logger.error(f"Failed to pre-load model: {e}")
        # Don't fail startup, will retry on first request

    yield

    logger.info("Shutting down SD server")


app = FastAPI(
    title="Stable Diffusion Service",
    description="SDXL Turbo image generation API",
    version="1.0.0",
    lifespan=lifespan,
)


class GenerateRequest(BaseModel):
    """Image generation request."""

    prompt: str = Field(..., description="Image description prompt")
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, deformed",
        description="Negative prompt",
    )
    width: int = Field(default=512, ge=256, le=1024, description="Image width")
    height: int = Field(default=768, ge=256, le=1024, description="Image height")
    num_inference_steps: int = Field(
        default=4, ge=1, le=50, description="Number of inference steps"
    )
    guidance_scale: float = Field(
        default=0.0, ge=0.0, le=20.0, description="CFG scale (0 for Turbo)"
    )
    seed: int | None = Field(default=None, description="Random seed for reproducibility")


class GenerateResponse(BaseModel):
    """Image generation response."""

    image: str = Field(..., description="Base64 encoded PNG image")
    width: int = Field(..., description="Generated image width")
    height: int = Field(..., description="Generated image height")
    seed: int = Field(..., description="Seed used for generation")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    device: str = Field(..., description="Inference device")
    model_loaded: bool = Field(..., description="Whether model is loaded")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Service health status
    """
    return HealthResponse(
        status="ok",
        device=_device,
        model_loaded=_pipeline is not None,
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate image from prompt.

    Args:
        request: Generation parameters

    Returns:
        Generated image as base64

    Raises:
        HTTPException: If generation fails
    """
    global _pipeline

    # Lazy load pipeline if not loaded
    if _pipeline is None:
        try:
            _pipeline = _load_pipeline()
        except Exception as e:
            logger.error(f"Failed to load pipeline: {e}")
            raise HTTPException(status_code=503, detail=f"Model loading failed: {e}") from e

    # Set seed for reproducibility
    if request.seed is not None:
        generator = torch.Generator(device=_device).manual_seed(request.seed)
        seed = request.seed
    else:
        seed = int(torch.randint(0, 2**32, (1,)).item())
        generator = torch.Generator(device=_device).manual_seed(seed)

    try:
        logger.info(
            f"Generating image: {request.prompt[:50]}... "
            f"({request.width}x{request.height}, steps={request.num_inference_steps})"
        )

        result = _pipeline(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=request.width,
            height=request.height,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            generator=generator,
        )

        image = result.images[0]
        image_base64 = _image_to_base64(image)

        logger.info(f"Image generated successfully (seed={seed})")

        return GenerateResponse(
            image=image_base64,
            width=request.width,
            height=request.height,
            seed=seed,
        )

    except Exception as e:
        logger.error(f"Generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e


@app.get("/")
async def root() -> dict[str, str | dict[str, str]]:
    """Root endpoint with API info."""
    return {
        "service": "Stable Diffusion",
        "model": "SDXL Turbo",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "generate": "/generate",
        },
    }
