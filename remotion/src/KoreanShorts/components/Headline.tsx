import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SafeZone, SceneType, TextAnimation, Theme } from "../types";

interface HeadlineProps {
  line1: string;
  line2: string;
  accentColor: string; // legacy fallback
  safeZone?: SafeZone;
  theme?: Theme;
  animation?: TextAnimation;
  /** Current scene type — adjusts headline pulse for persona/emphasis scenes */
  currentSceneType?: SceneType;
  /** Seconds after which the headline fades out (default: 3.0) */
  exitAfterSeconds?: number;
}

const DEFAULT_SAFE_ZONE: SafeZone = {
  top_px: 380,
  bottom_px: 480,
  left_px: 120,
  right_px: 120,
};

/** Text outline via multi-directional text-shadow for readability on any background */
function makeOutlineShadow(color: string, size: number): string {
  return [
    `${-size}px ${-size}px 0 ${color}`,
    `${size}px ${-size}px 0 ${color}`,
    `${-size}px ${size}px 0 ${color}`,
    `${size}px ${size}px 0 ${color}`,
    `0 ${-size}px 0 ${color}`,
    `0 ${size}px 0 ${color}`,
    `${-size}px 0 0 ${color}`,
    `${size}px 0 0 ${color}`,
    `0 0 12px rgba(0,0,0,0.6)`,
  ].join(", ");
}

/**
 * Top headline area for Korean Shorts.
 *
 * Uses a top-to-transparent gradient instead of a solid background band
 * so the background visual shows through naturally.
 *
 * Text readability is ensured via heavy outline + drop shadow.
 *
 * Entrance: Line 1 slides from left with spring physics,
 * Line 2 slides from right with a staggered delay.
 */
export const Headline: React.FC<HeadlineProps> = ({
  line1,
  line2,
  accentColor,
  safeZone,
  theme,
  currentSceneType,
  exitAfterSeconds = 3.0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!line1 && !line2) return null;

  const sz = safeZone ?? DEFAULT_SAFE_ZONE;
  const fontFamily = `'${theme?.font_family ?? "Pretendard"}', 'Noto Sans CJK KR', sans-serif`;
  const line1Color = theme?.accent_color ?? accentColor;
  const line2Color = theme?.secondary_color ?? "#FFFFFF";
  const fontSize1 = theme?.headline_font_size_line1 ?? 110;
  const fontSize2 = theme?.headline_font_size_line2 ?? 80;

  // --- Container entrance: fade in over 12 frames ---
  const entranceOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });

  // --- Exit: fade out after exitAfterSeconds ---
  const exitStartFrame = Math.round(exitAfterSeconds * fps);
  const exitDurationFrames = 20;
  const exitOpacity = interpolate(
    frame,
    [exitStartFrame, exitStartFrame + exitDurationFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const containerOpacity = entranceOpacity * exitOpacity;

  // --- Line 1: spring slide from left ---
  const line1Spring = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 120, mass: 0.8 },
  });
  const line1TranslateX = interpolate(line1Spring, [0, 1], [-60, 0]);
  const line1Scale = interpolate(line1Spring, [0, 1], [0.9, 1.0]);

  // --- Line 2: spring slide from right with 8-frame delay ---
  const line2Delay = 8;
  const line2Spring = spring({
    frame: Math.max(0, frame - line2Delay),
    fps,
    config: { damping: 15, stiffness: 120, mass: 0.8 },
  });
  const line2TranslateX = interpolate(line2Spring, [0, 1], [60, 0]);
  const line2Scale = interpolate(line2Spring, [0, 1], [0.9, 1.0]);

  // --- Scene-type glow for persona/emphasis ---
  const isPersona =
    currentSceneType === "commentary" || currentSceneType === "reaction";

  // Text outline for readability
  const outlineShadow = makeOutlineShadow("#000000", 4);
  const personaGlow = isPersona
    ? `, 0 0 24px ${line1Color}80, 0 0 48px ${line1Color}40`
    : "";

  return (
    <AbsoluteFill>
      {/* Gradient overlay: top edge → transparent, so background shows through */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: sz.top_px + 320,
          background: "linear-gradient(to bottom, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.4) 60%, rgba(0,0,0,0) 100%)",
          opacity: containerOpacity,
          pointerEvents: "none",
        }}
      />

      {/* Text container: positioned below safe zone top */}
      <div
        style={{
          position: "absolute",
          top: sz.top_px,
          left: 0,
          right: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-start",
          alignItems: "center",
          padding: `0 ${Math.max(sz.left_px, sz.right_px)}px`,
          gap: 8,
          opacity: containerOpacity,
        }}
      >
        {line1 ? (
          <div
            style={{
              fontFamily,
              fontSize: fontSize1,
              fontWeight: 800,
              fontStyle: "italic",
              color: line1Color,
              textAlign: "center",
              lineHeight: 1.1,
              letterSpacing: "-2px",
              width: "100%",
              wordBreak: "keep-all",
              overflowWrap: "break-word",
              transform: `translateX(${line1TranslateX}px) scale(${line1Scale})`,
              textShadow: outlineShadow + personaGlow,
            }}
          >
            {line1}
          </div>
        ) : null}
        {line2 ? (
          <div
            style={{
              fontFamily,
              fontSize: fontSize2,
              fontWeight: 700,
              fontStyle: "italic",
              color: line2Color,
              textAlign: "center",
              lineHeight: 1.1,
              letterSpacing: "-1px",
              width: "100%",
              wordBreak: "keep-all",
              overflowWrap: "break-word",
              transform: `translateX(${line2TranslateX}px) scale(${line2Scale})`,
              textShadow: outlineShadow,
            }}
          >
            {line2}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
