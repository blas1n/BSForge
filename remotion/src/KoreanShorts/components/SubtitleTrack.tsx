import React from "react";
import {
  AbsoluteFill,
  interpolate,
  interpolateColors,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { SafeZone, SubtitleSegment, Theme } from "../types";

interface SubtitleTrackProps {
  segments: SubtitleSegment[];
  enableKaraoke: boolean;
  highlightColor?: string;
  textColor?: string;
  safeZone?: SafeZone;
  theme?: Theme;
  /** Emphasis words from current scene — rendered with accent color + scale */
  emphasisWords?: string[];
  /** Accent color for emphasis words */
  accentColor?: string;
}

/** Frames for segment fade-in / fade-out animations */
const FADE_IN_FRAMES = 5;
const FADE_OUT_FRAMES = 4;

/** Frames for karaoke color transition per word */
const KARAOKE_BLEND_FRAMES = 3;

/**
 * Karaoke-style subtitle track with smooth animations.
 *
 * - Per-segment fade-in (opacity + translateY) and fade-out
 * - Smooth karaoke word color transition via interpolateColors()
 * - Emphasis words rendered with accent color and slight scale-up
 */
export const SubtitleTrack: React.FC<SubtitleTrackProps> = ({
  segments,
  enableKaraoke,
  highlightColor = "#FFFF00",
  textColor = "#FFFFFF",
  safeZone,
  theme,
  emphasisWords = [],
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const { fps, height: videoHeight } = useVideoConfig();

  const currentTimeSec = frame / fps;

  const activeSegment = segments.find(
    (seg) => currentTimeSec >= seg.start && currentTimeSec < seg.end,
  );

  if (!activeSegment) return null;

  const resolvedHighlight = theme?.highlight_color ?? highlightColor;
  const resolvedTextColor = theme?.text_color ?? textColor;
  const resolvedFontSize = theme?.subtitle_font_size ?? 100;
  const resolvedOutlineColor = theme?.outline_color ?? "#000000";
  const fontFamily = `'${theme?.font_family ?? "Pretendard"}', 'Noto Sans CJK KR', sans-serif`;
  const resolvedAccent = accentColor ?? theme?.accent_color ?? resolvedHighlight;

  // Position above bottom safe zone
  const bottomMargin = safeZone?.bottom_px ?? 480;
  const subtitleBlockHeight = resolvedFontSize * 1.25 * 2 + 40;
  const topPosition = videoHeight - bottomMargin - subtitleBlockHeight;

  // --- Per-segment fade-in / fade-out ---
  const segStartFrame = Math.round(activeSegment.start * fps);
  const segEndFrame = Math.round(activeSegment.end * fps);
  const framesIn = frame - segStartFrame;
  const framesOut = segEndFrame - frame;

  const fadeInOpacity = interpolate(framesIn, [0, FADE_IN_FRAMES], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeInY = interpolate(framesIn, [0, FADE_IN_FRAMES], [12, 0], {
    extrapolateRight: "clamp",
  });
  const fadeOutOpacity = interpolate(
    framesOut,
    [0, FADE_OUT_FRAMES],
    [0, 1],
    { extrapolateRight: "clamp" },
  );

  const segmentOpacity = Math.min(fadeInOpacity, fadeOutOpacity);
  const segmentTranslateY = fadeInY;

  // Check if a word is an emphasis word (exact match or starts with emphasis word)
  const isEmphasis = (word: string): boolean => {
    if (emphasisWords.length === 0) return false;
    const clean = word.trim();
    return emphasisWords.some((ew) => clean === ew || clean.startsWith(ew));
  };

  // Karaoke: find current word progress for smooth color transition
  const renderText = () => {
    if (!enableKaraoke || !activeSegment.words) {
      return (
        <span style={{ color: resolvedTextColor }}>{activeSegment.text}</span>
      );
    }

    return (
      <>
        {activeSegment.words.map((wordObj, idx) => {
          // Smooth karaoke: interpolate color over KARAOKE_BLEND_FRAMES
          const wordStartFrame = Math.round(wordObj.start * fps);
          const wordEndFrame = Math.round(wordObj.end * fps);
          const isActive = frame >= wordStartFrame && frame < wordEndFrame;
          const isPast = frame >= wordEndFrame;
          const emphasis = isEmphasis(wordObj.word);

          // Base color: white for upcoming, yellow for active/past
          let wordColor: string;
          if (isActive) {
            // Smooth transition into highlight color
            const blendProgress = interpolate(
              frame - wordStartFrame,
              [0, KARAOKE_BLEND_FRAMES],
              [0, 1],
              { extrapolateRight: "clamp" },
            );
            wordColor = interpolateColors(
              blendProgress,
              [0, 1],
              [resolvedTextColor, emphasis ? resolvedAccent : resolvedHighlight],
            );
          } else if (isPast) {
            wordColor = emphasis ? resolvedAccent : resolvedHighlight;
          } else {
            wordColor = resolvedTextColor;
          }

          // Emphasis words get a slight scale bump
          const wordScale = emphasis && (isActive || isPast) ? 1.12 : isActive ? 1.05 : 1.0;

          return (
            <span
              key={idx}
              style={{
                color: wordColor,
                display: "inline-block",
                transform: `scale(${wordScale})`,
                transformOrigin: "bottom center",
                marginRight:
                  idx < activeSegment.words!.length - 1
                    ? "0.25em"
                    : undefined,
              }}
            >
              {wordObj.word}
            </span>
          );
        })}
      </>
    );
  };

  const outlineSize = 3;
  const textShadow = [
    `-${outlineSize}px -${outlineSize}px 0 ${resolvedOutlineColor}`,
    `${outlineSize}px -${outlineSize}px 0 ${resolvedOutlineColor}`,
    `-${outlineSize}px ${outlineSize}px 0 ${resolvedOutlineColor}`,
    `${outlineSize}px ${outlineSize}px 0 ${resolvedOutlineColor}`,
    `-${outlineSize}px 0 0 ${resolvedOutlineColor}`,
    `${outlineSize}px 0 0 ${resolvedOutlineColor}`,
    `0 -${outlineSize}px 0 ${resolvedOutlineColor}`,
    `0 ${outlineSize}px 0 ${resolvedOutlineColor}`,
  ].join(", ");

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          top: topPosition,
          left: safeZone?.left_px ?? 120,
          right: safeZone?.right_px ?? 120,
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          padding: "0 20px",
          opacity: segmentOpacity,
          transform: `translateY(${segmentTranslateY}px)`,
        }}
      >
        <div
          style={{
            fontFamily,
            fontSize: resolvedFontSize,
            fontWeight: 800,
            fontStyle: "italic",
            textAlign: "center",
            lineHeight: 1.25,
            textShadow,
            letterSpacing: "0px",
          }}
        >
          {renderText()}
        </div>
      </div>
    </AbsoluteFill>
  );
};
