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
}

const DEFAULT_SAFE_ZONE: SafeZone = {
  top_px: 380,
  bottom_px: 480,
  left_px: 120,
  right_px: 120,
};

/**
 * Top headline area for Korean Shorts.
 *
 * Positioned below the platform safe zone to avoid being hidden
 * by YouTube/TikTok UI overlays.
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
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!line1 && !line2) return null;

  const sz = safeZone ?? DEFAULT_SAFE_ZONE;
  const fontFamily = `'${theme?.font_family ?? "Pretendard"}', 'Noto Sans KR', sans-serif`;
  const line1Color = theme?.accent_color ?? accentColor;
  const line2Color = theme?.secondary_color ?? "#FFFFFF";
  const bgColor = theme?.headline_bg_color ?? "#000000";
  const bgOpacity = theme?.headline_bg_opacity ?? 0.82;
  const fontSize1 = theme?.headline_font_size_line1 ?? 110;
  const fontSize2 = theme?.headline_font_size_line2 ?? 80;

  // --- Container entrance: fade in over 12 frames ---
  const containerOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });

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
  const glowColor = isPersona ? line1Color : "transparent";
  const boxShadow = isPersona
    ? `inset 0 0 30px ${glowColor}40, 0 0 20px ${glowColor}30`
    : "none";

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          top: sz.top_px,
          left: 0,
          right: 0,
          height: 280,
          backgroundColor: `${bgColor}${Math.round(bgOpacity * 255)
            .toString(16)
            .padStart(2, "0")}`,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          padding: `0 ${Math.max(sz.left_px, sz.right_px)}px`,
          gap: 8,
          opacity: containerOpacity,
          boxShadow,
          transition: "box-shadow 0.3s ease",
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
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              transform: `translateX(${line1TranslateX}px) scale(${line1Scale})`,
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
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              transform: `translateX(${line2TranslateX}px) scale(${line2Scale})`,
            }}
          >
            {line2}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
