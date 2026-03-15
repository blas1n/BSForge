"""Wan 2.2 Text-to-Video API Server.

Runs as a standalone service in a Docker container.
Provides HTTP API for video generation using Wan 2.2 T2V model.

Endpoints:
    - /health: Health check
    - /generate: Text-to-video generation
    - /evaluate_video: CLIP-based text-video similarity (multi-frame)

Usage:
    uvicorn wan_server:app --host 0.0.0.0 --port 7861
"""

import base64
import logging
import os
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
import torch
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CLIP score normalization constants (same as SD service)
CLIP_SCORE_MIN = 0.15
CLIP_SCORE_MAX = 0.35

# Global model instances (lazy loaded)
_wan_pipeline: Any = None
_clip_model: Any = None
_clip_processor: Any = None
_device: str = "cpu"


def _detect_device() -> str:
    """Detect best available device for inference."""
    env_device = os.environ.get("WAN_DEVICE", "auto")
    if env_device != "auto":
        return env_device

    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_wan_pipeline() -> Any:
    """Load Wan 2.2 T2V pipeline from HuggingFace.

    Returns:
        Loaded WanPipeline instance
    """
    global _device
    _device = _detect_device()

    model_id = os.environ.get("WAN_MODEL_ID", "Wan-AI/Wan2.2-T2V-1.3B")
    logger.info(f"Loading Wan pipeline: {model_id} on device: {_device}")

    from diffusers import WanPipeline

    torch_dtype = torch.bfloat16 if _device in ("cuda", "mps") else torch.float32

    pipeline = WanPipeline.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
    )
    pipeline = pipeline.to(_device)

    if _device == "cuda":
        pipeline.enable_model_cpu_offload()

    logger.info(f"Wan pipeline loaded successfully on {_device}")
    return pipeline


def _load_clip_model() -> tuple[Any, Any]:
    """Load CLIP model for video evaluation."""
    from transformers import CLIPModel, CLIPProcessor

    logger.info("Loading CLIP model...")
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    global _device
    if _device == "cpu":
        _device = _detect_device()

    model = model.to(_device)
    model.eval()

    logger.info(f"CLIP model loaded on {_device}")
    return model, processor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Pre-load Wan pipeline on startup."""
    global _wan_pipeline
    logger.info("Starting Wan server, pre-loading pipeline...")

    try:
        _wan_pipeline = _load_wan_pipeline()
        logger.info("Wan pipeline pre-loaded successfully")
    except Exception as e:
        logger.error(f"Failed to pre-load Wan pipeline: {e}")

    yield

    logger.info("Shutting down Wan server")


app = FastAPI(
    title="Wan Video Service",
    description="Wan 2.2 T2V video generation API",
    version="1.0.0",
    lifespan=lifespan,
)


class WanGenerateRequest(BaseModel):
    """Video generation request."""

    prompt: str = Field(..., description="Video description prompt")
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, deformed, static, still, frozen",
        description="Negative prompt",
    )
    duration_seconds: float = Field(
        default=5.0, ge=2.0, le=10.0, description="Video duration in seconds"
    )
    width: int = Field(default=480, ge=256, le=1280, description="Video width")
    height: int = Field(default=832, ge=256, le=1280, description="Video height")
    fps: int = Field(default=16, ge=8, le=30, description="Frames per second")
    guidance_scale: float = Field(default=5.0, ge=1.0, le=10.0, description="CFG guidance scale")
    seed: int | None = Field(default=None, description="Random seed for reproducibility")


class WanGenerateResponse(BaseModel):
    """Video generation response."""

    video: str = Field(..., description="Base64 encoded MP4 video")
    duration_seconds: float = Field(..., description="Actual video duration")
    width: int = Field(..., description="Video width")
    height: int = Field(..., description="Video height")
    fps: int = Field(..., description="Frames per second")
    num_frames: int = Field(..., description="Number of frames generated")
    seed: int = Field(..., description="Seed used for generation")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    device: str = Field(..., description="Inference device")
    pipeline_loaded: bool = Field(..., description="Whether pipeline is loaded")
    clip_loaded: bool = Field(..., description="Whether CLIP model is loaded")
    model_id: str = Field(..., description="Model ID")


class EvaluateVideoRequest(BaseModel):
    """CLIP text-video similarity evaluation request."""

    video: str = Field(..., description="Base64 encoded video file")
    text: str = Field(..., description="Text/keyword to match against video")
    num_frames: int = Field(default=5, ge=1, le=10, description="Number of frames to sample")


class EvaluateVideoResponse(BaseModel):
    """CLIP video evaluation response."""

    score: float = Field(..., description="Average similarity score (0.0 to 1.0)")
    min_score: float = Field(..., description="Minimum frame score")
    max_score: float = Field(..., description="Maximum frame score")
    num_frames_evaluated: int = Field(..., description="Number of frames evaluated")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    model_id = os.environ.get("WAN_MODEL_ID", "Wan-AI/Wan2.2-T2V-1.3B")
    return HealthResponse(
        status="ok",
        device=_device,
        pipeline_loaded=_wan_pipeline is not None,
        clip_loaded=_clip_model is not None,
        model_id=model_id,
    )


@app.post("/generate", response_model=WanGenerateResponse)
async def generate(request: WanGenerateRequest) -> WanGenerateResponse:
    """Generate video from text prompt.

    Args:
        request: Generation parameters

    Returns:
        Generated video as base64 MP4

    Raises:
        HTTPException: If generation fails
    """
    global _wan_pipeline

    if _wan_pipeline is None:
        try:
            _wan_pipeline = _load_wan_pipeline()
        except Exception as e:
            logger.error(f"Failed to load Wan pipeline: {e}")
            raise HTTPException(status_code=503, detail=f"Model loading failed: {e}") from e

    # Set seed
    if request.seed is not None:
        generator = torch.Generator(device=_device).manual_seed(request.seed)
        seed = request.seed
    else:
        seed = int(torch.randint(0, 2**32, (1,)).item())
        generator = torch.Generator(device=_device).manual_seed(seed)

    num_frames = int(request.duration_seconds * request.fps)
    # Wan 2.2 requires num_frames to be 4k+1 for some schedulers
    # Round to nearest valid value (typically odd number works)
    if num_frames % 4 != 1:
        num_frames = (num_frames // 4) * 4 + 1

    try:
        logger.info(
            f"Generating video: '{request.prompt[:60]}...' "
            f"({request.width}x{request.height}, {num_frames} frames, "
            f"fps={request.fps}, seed={seed})"
        )

        output = _wan_pipeline(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            height=request.height,
            width=request.width,
            num_frames=num_frames,
            guidance_scale=request.guidance_scale,
            generator=generator,
        )

        frames = output.frames[0]
        actual_frames = len(frames)
        actual_duration = actual_frames / request.fps

        # Export to MP4 in temp file, read, encode as base64
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            from diffusers.utils import export_to_video

            export_to_video(frames, tmp_path, fps=request.fps)

            with open(tmp_path, "rb") as f:
                video_base64 = base64.b64encode(f.read()).decode("utf-8")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        logger.info(
            f"Video generated successfully: {actual_frames} frames, "
            f"{actual_duration:.1f}s (seed={seed})"
        )

        return WanGenerateResponse(
            video=video_base64,
            duration_seconds=actual_duration,
            width=request.width,
            height=request.height,
            fps=request.fps,
            num_frames=actual_frames,
            seed=seed,
        )

    except Exception as e:
        logger.error(f"Video generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e


def _extract_video_frames(video_data: bytes, num_frames: int = 5) -> list[Image.Image]:
    """Extract frames uniformly from video data."""
    frames = []

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_data)
        temp_path = f.name

    try:
        cap = cv2.VideoCapture(temp_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            logger.warning("Could not get frame count from video")
            return []

        if total_frames <= num_frames:
            indices = list(range(total_frames))
        else:
            start_frame = int(total_frames * 0.1)
            end_frame = int(total_frames * 0.9)
            step = (end_frame - start_frame) / (num_frames - 1) if num_frames > 1 else 0
            indices = [int(start_frame + i * step) for i in range(num_frames)]

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(Image.fromarray(rgb_frame))

        cap.release()
    finally:
        os.unlink(temp_path)

    return frames


@app.post("/evaluate_video", response_model=EvaluateVideoResponse)
async def evaluate_video(request: EvaluateVideoRequest) -> EvaluateVideoResponse:
    """Evaluate text-video similarity using CLIP.

    Args:
        request: Evaluation parameters

    Returns:
        Average, min, and max similarity scores

    Raises:
        HTTPException: If evaluation fails
    """
    global _clip_model, _clip_processor

    if _clip_model is None or _clip_processor is None:
        try:
            _clip_model, _clip_processor = _load_clip_model()
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise HTTPException(status_code=503, detail=f"CLIP model loading failed: {e}") from e

    try:
        video_data = base64.b64decode(request.video)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid video encoding: {e}") from e

    try:
        frames = _extract_video_frames(video_data, request.num_frames)
        if not frames:
            raise HTTPException(status_code=400, detail="Could not extract frames from video")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Frame extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Frame extraction failed: {e}") from e

    try:
        scores = []
        for frame in frames:
            inputs = _clip_processor(
                text=[request.text],
                images=frame,
                return_tensors="pt",
                padding=True,
            )
            inputs = {k: v.to(_device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = _clip_model(**inputs)
                similarity = torch.nn.functional.cosine_similarity(
                    outputs.image_embeds, outputs.text_embeds
                ).item()

            score = max(
                0.0, min(1.0, (similarity - CLIP_SCORE_MIN) / (CLIP_SCORE_MAX - CLIP_SCORE_MIN))
            )
            scores.append(score)

        avg_score = sum(scores) / len(scores)
        logger.info(f"Video eval '{request.text[:40]}': avg={avg_score:.4f}")

        return EvaluateVideoResponse(
            score=avg_score,
            min_score=min(scores),
            max_score=max(scores),
            num_frames_evaluated=len(scores),
        )

    except Exception as e:
        logger.error(f"Video evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}") from e


@app.get("/")
async def root() -> dict[str, str | dict[str, str]]:
    """Root endpoint with API info."""
    return {
        "service": "Wan Video Service",
        "model": os.environ.get("WAN_MODEL_ID", "Wan-AI/Wan2.2-T2V-1.3B"),
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "generate": "/generate (T2V)",
            "evaluate_video": "/evaluate_video (CLIP)",
        },
    }
