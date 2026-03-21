import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SafeZone, SceneInfo, Theme } from "../types";

interface KineticTypographyProps {
  scenes: SceneInfo[];
  theme?: Theme;
  safeZone?: SafeZone;
}

/** Duration (seconds) the keyword badge stays on screen. */
const DISPLAY_SECONDS = 0.7;

/** Text shadow for maximum readability on any background. */
const TEXT_SHADOW = [
  "-4px -4px 0 #000",
  "4px -4px 0 #000",
  "-4px 4px 0 #000",
  "4px 4px 0 #000",
  "0 0 40px rgba(0,0,0,0.9)",
].join(", ");

/**
 * Kinetic Typography overlay.
 *
 * At the start of each scene that has emphasis_words, pops the first
 * emphasis word into the center of the frame with a spring-bounce entrance,
 * then fades out before the 1-second mark.
 *
 * Layered between Headline and SubtitleTrack so it never obscures subtitles.
 */
export const KineticTypography: React.FC<KineticTypographyProps> = ({
  scenes,
  theme,
  safeZone,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTimeSec = frame / fps;

  const displayFrames = Math.round(fps * DISPLAY_SECONDS);
  const safeLeft = safeZone?.left_px ?? 120;
  const safeRight = safeZone?.right_px ?? 120;
  const accentColor = theme?.accent_color ?? "#FF6B6B";
  const fontFamily = `'${theme?.font_family ?? "Pretendard"}', 'Noto Sans CJK KR', sans-serif`;

  // Find the scene that just started and has emphasis words
  const activeScene = scenes.find(
    (s) =>
      currentTimeSec >= s.start_time &&
      currentTimeSec < s.start_time + DISPLAY_SECONDS &&
      s.emphasis_words.length > 0,
  );

  if (!activeScene) return null;

  const keyword = activeScene.emphasis_words[0];
  const sceneStartFrame = Math.round(activeScene.start_time * fps);
  const elapsed = frame - sceneStartFrame;

  if (elapsed < 0 || elapsed > displayFrames) return null;

  // Spring pop-in: scale 0.3 → 1.0 with slight overshoot
  const scaleSpring = spring({
    frame: elapsed,
    fps,
    config: { damping: 14, stiffness: 260, mass: 0.55 },
  });
  const scale = interpolate(scaleSpring, [0, 1], [0.3, 1.0]);

  // Opacity: fade in fast (4 frames), hold, fade out last 8 frames
  const fadeOutStart = displayFrames - 8;
  const opacity = interpolate(
    elapsed,
    [0, 4, fadeOutStart, displayFrames],
    [0, 1, 1, 0],
    { extrapolateRight: "clamp" },
  );

  // Subtle vertical drift: floats upward 10px over the display window
  const translateY = interpolate(elapsed, [0, displayFrames], [0, -10], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          paddingLeft: safeLeft,
          paddingRight: safeRight,
          opacity,
          transform: `scale(${scale}) translateY(${translateY}px)`,
        }}
      >
        <div
          style={{
            fontFamily,
            fontSize: 152,
            fontWeight: 900,
            fontStyle: "italic",
            color: accentColor,
            textAlign: "center",
            lineHeight: 1.0,
            textShadow: TEXT_SHADOW,
            wordBreak: "keep-all",
            letterSpacing: "-3px",
          }}
        >
          {keyword}
        </div>
      </div>
    </AbsoluteFill>
  );
};
