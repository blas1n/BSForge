#!/usr/bin/env python
"""Generate demo BGM and SFX assets using FFmpeg lavfi synthesis.

Produces royalty-free audio for local testing without any external API calls.

Assets generated:
  data/bgm/ambient_lofi.mp3   — 60s lo-fi ambient (528Hz + brown noise blend)
  data/sfx/whoosh.mp3         — scene transition whoosh (0.4s)
  data/sfx/pop.mp3            — emphasis pop (0.15s)
  data/sfx/ding.mp3           — CTA success ding (0.6s)

Run with: uv run python scripts/setup_demo_assets.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BGM_DIR = Path("data/bgm")
SFX_DIR = Path("data/sfx")


def _run(cmd: list[str], label: str) -> None:
    """Run a shell command and print result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"   WARN: {label} failed:\n{result.stderr[:300]}", file=sys.stderr)
    else:
        print(f"   OK: {label}")


def generate_bgm() -> None:
    """Generate 60s lo-fi ambient BGM.

    528 Hz sine (relaxing tone) mixed with very-low-amplitude noise,
    then compressed slightly for consistent loudness.
    """
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    output = BGM_DIR / "ambient_lofi.mp3"
    if output.exists():
        print(f"   skip (exists): {output}")
        return

    # Two-source mix: 528Hz sine (main tone) + white noise (ambient texture)
    # Volume envelope: -14 LUFS target for voice ducking compatibility
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=528:sample_rate=44100",
        "-f",
        "lavfi",
        "-i",
        "aevalsrc=0.015*random(0)+0.015*random(1):s=44100:c=stereo",
        "-filter_complex",
        (
            "[0]volume=0.25[tone];"
            "[1]volume=0.8,lowpass=f=400[noise];"
            "[tone][noise]amix=inputs=2:duration=shortest,"
            "afade=t=in:st=0:d=4,"
            "afade=t=out:st=56:d=4,"
            "loudnorm=I=-18:TP=-2:LRA=7"
        ),
        "-t",
        "60",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "4",
        str(output),
    ]
    _run(cmd, f"BGM → {output}")


def generate_sfx() -> None:
    """Generate whoosh, pop, ding SFX using FFmpeg aevalsrc synthesis."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    sfx_specs: list[tuple[str, float, str]] = [
        # (filename, duration_s, aevalsrc_expr + afade chain)
        (
            "whoosh.mp3",
            0.5,
            # Noise burst with bandpass to simulate a swoosh
            "aevalsrc=0.4*random(0)*exp(-3*t):s=44100:d=0.5",
        ),
        (
            "pop.mp3",
            0.2,
            # Short 880Hz burst with fast exponential decay
            "aevalsrc=0.6*sin(2*PI*880*t)*exp(-15*t):s=44100:d=0.2",
        ),
        (
            "ding.mp3",
            0.7,
            # Two harmonics (C6 + G6) for a pleasant bell tone
            "aevalsrc=0.4*sin(2*PI*1047*t)*exp(-5*t)+0.25*sin(2*PI*1568*t)*exp(-6*t):s=44100:d=0.7",
        ),
    ]

    for filename, duration, aevalsrc_expr in sfx_specs:
        output = SFX_DIR / filename
        if output.exists():
            print(f"   skip (exists): {output}")
            continue

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            aevalsrc_expr,
            "-af",
            f"afade=t=out:st={duration * 0.7:.2f}:d={duration * 0.3:.2f},volume=0.9",
            "-t",
            str(duration),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(output),
        ]
        _run(cmd, f"SFX  → {output}")


def main() -> None:
    """Generate all demo assets."""
    print("Generating demo BGM + SFX assets...")
    generate_bgm()
    generate_sfx()
    print("\nDone. Files:")
    for f in sorted((*BGM_DIR.glob("*.mp3"), *SFX_DIR.glob("*.mp3"))):
        size_kb = f.stat().st_size // 1024
        print(f"  {f}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
