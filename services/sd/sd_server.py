"""Stable Diffusion API Server.

Runs as a standalone service in a Docker container.
Provides HTTP API for image generation using RealVisXL V5.0 Lightning.

Endpoints:
    - /health: Health check
    - /generate: Text-to-image generation (txt2img)
    - /img2img: Image-to-image transformation
    - /evaluate: CLIP-based text-image similarity evaluation
    - /evaluate_video: CLIP-based text-video similarity (multi-frame)

Usage:
    uvicorn sd_server:app --host 0.0.0.0 --port 7860
"""

import base64
import io
import logging
import os
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import cv2
import torch
from diffusers import AutoPipelineForImage2Image, AutoPipelineForText2Image
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CLIP score normalization constants
# Raw CLIP cosine similarity typically ranges from 0.15 (unrelated) to 0.35 (good match)
# We scale this range to 0-1 for more intuitive thresholding
CLIP_SCORE_MIN = 0.15  # Baseline for unrelated content
CLIP_SCORE_MAX = 0.35  # Typical max for good semantic match

# Global pipeline instances (lazy loaded)
_txt2img_pipeline: Any = None
_img2img_pipeline: Any = None
_clip_model: Any = None
_clip_processor: Any = None
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


def _load_txt2img_pipeline() -> Any:
    """Load RealVisXL V5.0 Lightning text-to-image pipeline.

    Uses RealVisXL V5.0 Lightning - a high quality photorealistic model
    that generates in 4-8 steps with good quality.

    Returns:
        Loaded diffusion pipeline
    """
    global _device
    _device = _detect_device()

    logger.info(f"Loading RealVisXL V5.0 Lightning txt2img on device: {_device}")

    # Determine torch dtype based on device
    torch_dtype = torch.float16 if _device in ("cuda", "mps") else torch.float32

    # RealVisXL V5.0 Lightning - high quality photorealistic model
    # Uses Lightning scheduler for fast inference (4-8 steps)
    pipeline = AutoPipelineForText2Image.from_pretrained(
        "SG161222/RealVisXL_V5.0_Lightning",
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

    logger.info(f"RealVisXL V5.0 Lightning txt2img loaded successfully on {_device}")
    return pipeline


def _load_img2img_pipeline() -> Any:
    """Load RealVisXL V5.0 Lightning image-to-image pipeline.

    Returns:
        Loaded diffusion pipeline
    """
    global _device
    if _device == "cpu":
        _device = _detect_device()

    logger.info(f"Loading RealVisXL V5.0 Lightning img2img on device: {_device}")

    torch_dtype = torch.float16 if _device in ("cuda", "mps") else torch.float32

    pipeline = AutoPipelineForImage2Image.from_pretrained(
        "SG161222/RealVisXL_V5.0_Lightning",
        torch_dtype=torch_dtype,
        variant="fp16" if torch_dtype == torch.float16 else None,
    )

    pipeline = pipeline.to(_device)

    if _device == "cuda":
        pipeline.enable_model_cpu_offload()
    elif _device != "mps":
        pipeline.enable_sequential_cpu_offload()

    logger.info(f"RealVisXL V5.0 Lightning img2img loaded successfully on {_device}")
    return pipeline


def _load_clip_model() -> tuple[Any, Any]:
    """Load CLIP model for text-image similarity evaluation.

    Returns:
        Tuple of (model, processor)
    """
    from transformers import CLIPModel, CLIPProcessor

    logger.info("Loading CLIP model...")

    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    # Move to device
    global _device
    if _device == "cpu":
        _device = _detect_device()

    model = model.to(_device)
    model.eval()

    logger.info(f"CLIP model loaded successfully on {_device}")
    return model, processor


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


def _base64_to_image(base64_string: str) -> Image.Image:
    """Convert base64 string to PIL Image.

    Args:
        base64_string: Base64 encoded image

    Returns:
        PIL Image

    Raises:
        ValueError: If image cannot be decoded
    """
    try:
        image_data = base64.b64decode(base64_string)
        buffer = io.BytesIO(image_data)
        img = Image.open(buffer)
        # Force load to detect format errors early
        img.load()
        return img.convert("RGB")
    except Exception as e:
        # Log the first few bytes to help debug format issues
        data_preview = base64_string[:50] if len(base64_string) > 50 else base64_string
        logger.error(f"Failed to decode image. Preview: {data_preview}..., Error: {e}")
        raise ValueError(f"Cannot decode image: {e}") from e


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Pre-loads the txt2img model on startup for faster first inference.
    Other models (img2img, CLIP) are lazy-loaded on first request.
    """
    global _txt2img_pipeline
    logger.info("Starting SD server, pre-loading txt2img model...")

    try:
        _txt2img_pipeline = _load_txt2img_pipeline()
        logger.info("txt2img model pre-loaded successfully")
    except Exception as e:
        logger.error(f"Failed to pre-load txt2img model: {e}")
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
    txt2img_loaded: bool = Field(..., description="Whether txt2img model is loaded")
    img2img_loaded: bool = Field(..., description="Whether img2img model is loaded")
    clip_loaded: bool = Field(..., description="Whether CLIP model is loaded")


class Img2ImgRequest(BaseModel):
    """Image-to-image transformation request."""

    image: str = Field(..., description="Base64 encoded input image")
    prompt: str = Field(..., description="Image description prompt")
    negative_prompt: str = Field(
        default="blurry, low quality, distorted, deformed",
        description="Negative prompt",
    )
    strength: float = Field(default=0.5, ge=0.1, le=0.9, description="Transformation strength")
    num_inference_steps: int = Field(
        default=4, ge=1, le=50, description="Number of inference steps"
    )
    guidance_scale: float = Field(
        default=0.0, ge=0.0, le=20.0, description="CFG scale (0 for Turbo)"
    )
    seed: int | None = Field(default=None, description="Random seed for reproducibility")


class EvaluateRequest(BaseModel):
    """CLIP text-image similarity evaluation request."""

    image: str = Field(..., description="Base64 encoded image")
    text: str = Field(..., description="Text/keyword to match against image")


class EvaluateResponse(BaseModel):
    """CLIP evaluation response."""

    score: float = Field(..., description="Similarity score (0.0 to 1.0)")


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
    """Health check endpoint.

    Returns:
        Service health status
    """
    return HealthResponse(
        status="ok",
        device=_device,
        txt2img_loaded=_txt2img_pipeline is not None,
        img2img_loaded=_img2img_pipeline is not None,
        clip_loaded=_clip_model is not None,
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate image from text prompt (txt2img).

    Args:
        request: Generation parameters

    Returns:
        Generated image as base64

    Raises:
        HTTPException: If generation fails
    """
    global _txt2img_pipeline

    # Lazy load pipeline if not loaded
    if _txt2img_pipeline is None:
        try:
            _txt2img_pipeline = _load_txt2img_pipeline()
        except Exception as e:
            logger.error(f"Failed to load txt2img pipeline: {e}")
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

        result = _txt2img_pipeline(
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


@app.post("/img2img", response_model=GenerateResponse)
async def img2img(request: Img2ImgRequest) -> GenerateResponse:
    """Transform image based on prompt (img2img).

    Args:
        request: Transformation parameters

    Returns:
        Transformed image as base64

    Raises:
        HTTPException: If transformation fails
    """
    global _img2img_pipeline

    # Lazy load pipeline if not loaded
    if _img2img_pipeline is None:
        try:
            _img2img_pipeline = _load_img2img_pipeline()
        except Exception as e:
            logger.error(f"Failed to load img2img pipeline: {e}")
            raise HTTPException(status_code=503, detail=f"Model loading failed: {e}") from e

    # Decode input image
    try:
        input_image = _base64_to_image(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}") from e

    # Set seed for reproducibility
    if request.seed is not None:
        generator = torch.Generator(device=_device).manual_seed(request.seed)
        seed = request.seed
    else:
        seed = int(torch.randint(0, 2**32, (1,)).item())
        generator = torch.Generator(device=_device).manual_seed(seed)

    try:
        logger.info(
            f"Transforming image: {request.prompt[:50]}... "
            f"(strength={request.strength}, steps={request.num_inference_steps})"
        )

        result = _img2img_pipeline(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            image=input_image,
            strength=request.strength,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            generator=generator,
        )

        image = result.images[0]
        image_base64 = _image_to_base64(image)

        logger.info(f"Image transformed successfully (seed={seed})")

        return GenerateResponse(
            image=image_base64,
            width=image.width,
            height=image.height,
            seed=seed,
        )

    except Exception as e:
        logger.error(f"Transformation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transformation failed: {e}") from e


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    """Evaluate text-image similarity using CLIP.

    Args:
        request: Evaluation parameters

    Returns:
        Similarity score (0.0 to 1.0)

    Raises:
        HTTPException: If evaluation fails
    """
    global _clip_model, _clip_processor

    # Lazy load CLIP model if not loaded
    if _clip_model is None or _clip_processor is None:
        try:
            _clip_model, _clip_processor = _load_clip_model()
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise HTTPException(status_code=503, detail=f"CLIP model loading failed: {e}") from e

    # Decode input image
    try:
        image = _base64_to_image(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image: {e}") from e

    try:
        logger.info(f"Evaluating image-text similarity: {request.text[:50]}...")

        # Process inputs
        inputs = _clip_processor(
            text=[request.text],
            images=image,
            return_tensors="pt",
            padding=True,
        )

        # Move to device
        inputs = {k: v.to(_device) for k, v in inputs.items()}

        # Get embeddings
        with torch.no_grad():
            outputs = _clip_model(**inputs)
            # Get normalized features
            image_features = outputs.image_embeds
            text_features = outputs.text_embeds

            # Compute cosine similarity
            similarity = torch.nn.functional.cosine_similarity(image_features, text_features).item()

        # Normalize to 0-1 range: (raw - min) / (max - min), clamped to [0, 1]
        score = max(
            0.0, min(1.0, (similarity - CLIP_SCORE_MIN) / (CLIP_SCORE_MAX - CLIP_SCORE_MIN))
        )

        logger.info(f"Similarity score: {score:.4f} (raw: {similarity:.4f})")

        return EvaluateResponse(score=score)

    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}") from e


def _extract_video_frames(video_data: bytes, num_frames: int = 5) -> list[Image.Image]:
    """Extract frames from video data.

    Samples frames uniformly across the video duration, avoiding first/last 10%.

    Args:
        video_data: Raw video bytes
        num_frames: Number of frames to extract

    Returns:
        List of PIL Images
    """
    frames = []

    # Write to temp file (cv2 needs file path)
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(video_data)
        temp_path = f.name

    try:
        cap = cv2.VideoCapture(temp_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if total_frames <= 0:
            logger.warning("Could not get frame count from video")
            return []

        # Calculate frame indices to sample (uniform distribution)
        if total_frames <= num_frames:
            indices = list(range(total_frames))
        else:
            # Sample uniformly, avoiding first and last 10%
            start_frame = int(total_frames * 0.1)
            end_frame = int(total_frames * 0.9)
            step = (end_frame - start_frame) / (num_frames - 1) if num_frames > 1 else 0
            indices = [int(start_frame + i * step) for i in range(num_frames)]

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                # Convert BGR to RGB
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_frame)
                frames.append(pil_image)

        cap.release()

    finally:
        os.unlink(temp_path)

    logger.info(f"Extracted {len(frames)} frames from video")
    return frames


@app.post("/evaluate_video", response_model=EvaluateVideoResponse)
async def evaluate_video(request: EvaluateVideoRequest) -> EvaluateVideoResponse:
    """Evaluate text-video similarity using CLIP with multi-frame sampling.

    Extracts multiple frames from the video and computes average CLIP score.

    Args:
        request: Evaluation parameters

    Returns:
        Average, min, and max similarity scores

    Raises:
        HTTPException: If evaluation fails
    """
    global _clip_model, _clip_processor

    # Lazy load CLIP model if not loaded
    if _clip_model is None or _clip_processor is None:
        try:
            _clip_model, _clip_processor = _load_clip_model()
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}")
            raise HTTPException(status_code=503, detail=f"CLIP model loading failed: {e}") from e

    # Decode video
    try:
        video_data = base64.b64decode(request.video)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid video encoding: {e}") from e

    # Extract frames
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
        logger.info(f"Evaluating {len(frames)} frames for: {request.text[:50]}...")

        scores = []
        for frame in frames:
            # Process inputs
            inputs = _clip_processor(
                text=[request.text],
                images=frame,
                return_tensors="pt",
                padding=True,
            )

            # Move to device
            inputs = {k: v.to(_device) for k, v in inputs.items()}

            # Get embeddings
            with torch.no_grad():
                outputs = _clip_model(**inputs)
                image_features = outputs.image_embeds
                text_features = outputs.text_embeds

                # Compute cosine similarity
                similarity = torch.nn.functional.cosine_similarity(
                    image_features, text_features
                ).item()

            # Normalize to 0-1 range
            score = max(
                0.0, min(1.0, (similarity - CLIP_SCORE_MIN) / (CLIP_SCORE_MAX - CLIP_SCORE_MIN))
            )
            scores.append(score)

        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)

        logger.info(
            f"Video evaluation: avg={avg_score:.4f}, " f"min={min_score:.4f}, max={max_score:.4f}"
        )

        return EvaluateVideoResponse(
            score=avg_score,
            min_score=min_score,
            max_score=max_score,
            num_frames_evaluated=len(scores),
        )

    except Exception as e:
        logger.error(f"Video evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}") from e


@app.get("/")
async def root() -> dict[str, str | dict[str, str]]:
    """Root endpoint with API info."""
    return {
        "service": "Stable Diffusion",
        "model": "RealVisXL V5.0 Lightning",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "generate": "/generate (txt2img)",
            "evaluate_video": "/evaluate_video (CLIP video)",
            "img2img": "/img2img",
            "evaluate": "/evaluate (CLIP)",
        },
    }
