import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SceneInfo, VisualStyle } from "../types";

interface SceneOverlayProps {
  currentScene: SceneInfo | null;
  accentColor: string;
}

/** Frames to transition overlay between scenes */
const OVERLAY_TRANSITION_FRAMES = 8;

/**
 * Scene-type visual overlay between background and text layers.
 *
 * Applies different treatments per VisualStyle:
 * - neutral:  30% black overlay (standard)
 * - persona:  40% dark overlay + accent-color left border + glow
 * - emphasis: 55% dark overlay + radial gradient vignette
 *
 * CTA scenes get a pulsing accent glow effect.
 */
export const SceneOverlay: React.FC<SceneOverlayProps> = ({
  currentScene,
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const visualStyle: VisualStyle = currentScene?.visual_style ?? "neutral";
  const sceneType = currentScene?.scene_type;

  // Fade in overlay at scene start
  const sceneStartFrame = currentScene
    ? Math.round(currentScene.start_time * fps)
    : 0;
  const elapsed = frame - sceneStartFrame;
  const transitionProgress = interpolate(
    elapsed,
    [0, OVERLAY_TRANSITION_FRAMES],
    [0, 1],
    { extrapolateRight: "clamp", extrapolateLeft: "clamp" },
  );

  // CTA pulse: sine wave glow
  const isCta = sceneType === "cta";
  const ctaPulse = isCta
    ? 0.3 + 0.15 * Math.sin((frame / fps) * Math.PI * 3)
    : 0;

  if (visualStyle === "persona") {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: `rgba(0, 0, 0, ${0.4 * transitionProgress})`,
          borderLeft: `6px solid ${accentColor}`,
          boxShadow: `inset 8px 0 24px ${accentColor}40, inset -2px 0 12px ${accentColor}20`,
          opacity: transitionProgress,
          pointerEvents: "none",
        }}
      />
    );
  }

  if (visualStyle === "emphasis") {
    return (
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at center, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0.65) 100%)`,
          opacity: transitionProgress,
          pointerEvents: "none",
        }}
      />
    );
  }

  // Neutral or CTA
  return (
    <AbsoluteFill
      style={{
        backgroundColor: `rgba(0, 0, 0, ${0.3 * transitionProgress})`,
        boxShadow: isCta
          ? `inset 0 0 40px ${accentColor}${Math.round(ctaPulse * 255)
              .toString(16)
              .padStart(2, "0")}`
          : "none",
        pointerEvents: "none",
      }}
    />
  );
};
