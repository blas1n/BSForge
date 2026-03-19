import React from "react";
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useVideoConfig,
} from "remotion";
import "../fonts"; // Register Pretendard font
import { KoreanShortsProps } from "./types";
import { useCurrentScene } from "./hooks/useCurrentScene";
import { BackgroundVisual } from "./components/BackgroundVisual";
import { Headline } from "./components/Headline";
import { KineticTypography } from "./components/KineticTypography";
import { SceneOverlay } from "./components/SceneOverlay";
import { SFXTrack } from "./components/SFXTrack";
import { SubtitleTrack } from "./components/SubtitleTrack";

/**
 * Korean Shorts composition.
 *
 * Layout (1080x1920) with safe zone awareness:
 * ┌─────────────────────────┐  0px
 * │   (platform UI zone)    │  ← top safe zone (380px)
 * ├─────────────────────────┤
 * │  Headline (animated)    │  ← below safe zone top
 * ├─────────────────────────┤
 * │   Background Visual     │  ← fullscreen (camera movement)
 * │   (with transitions)    │
 * ├─────────────────────────┤
 * │  Subtitles (animated)   │  ← above safe zone bottom
 * ├─────────────────────────┤
 * │   (platform UI zone)    │  ← bottom safe zone (480px)
 * └─────────────────────────┘  1920px
 *
 * Layer order (bottom to top):
 * 1. BackgroundVisual — camera movement + per-asset transitions
 * 2. SceneOverlay — scene-type visual differentiation
 * 3. Headline — spring entrance, scene-aware glow
 * 4. SubtitleTrack — karaoke with smooth color transitions
 * 5. Audio — TTS narration + BGM
 */
export const KoreanShorts: React.FC<KoreanShortsProps> = ({
  audio_path,
  bgm_path,
  bgm_volume,
  headline_line1,
  headline_line2,
  accent_color,
  visuals,
  subtitles,
  enable_ken_burns,
  enable_karaoke,
  headline_exit_after_seconds,
  safe_zone,
  theme,
  color_grading,
  scenes,
  sfx_paths,
}) => {
  const { durationInFrames } = useVideoConfig();
  const currentScene = useCurrentScene(scenes);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      {/* Layer 1: Background visuals (camera movement + transitions + color grading) */}
      <BackgroundVisual visuals={visuals} enableKenBurns={enable_ken_burns} colorGrading={color_grading} />

      {/* Layer 2: Scene-type overlay (persona border, emphasis vignette, CTA pulse) */}
      <SceneOverlay
        currentScene={currentScene}
        accentColor={theme?.accent_color ?? accent_color}
      />

      {/* Layer 3: Headline (spring entrance, scene-aware glow) */}
      <Headline
        line1={headline_line1}
        line2={headline_line2}
        accentColor={accent_color}
        safeZone={safe_zone}
        theme={theme}
        currentSceneType={currentScene?.scene_type}
        exitAfterSeconds={headline_exit_after_seconds}
      />

      {/* Layer 3.5: Kinetic typography — emphasis word pop-in at scene start */}
      {scenes && scenes.length > 0 && (
        <KineticTypography scenes={scenes} theme={theme} safeZone={safe_zone} />
      )}

      {/* Layer 4: Subtitles (fade-in/out, smooth karaoke, emphasis words) */}
      <SubtitleTrack
        segments={subtitles}
        enableKaraoke={enable_karaoke}
        highlightColor={theme?.highlight_color ?? "#FFFF00"}
        textColor={theme?.text_color ?? "#FFFFFF"}
        safeZone={safe_zone}
        theme={theme}
        emphasisWords={currentScene?.emphasis_words}
        accentColor={theme?.accent_color ?? accent_color}
      />

      {/* Layer 5: SFX — per-scene sound effects at scene boundaries */}
      {scenes && scenes.length > 0 && sfx_paths && Object.keys(sfx_paths).length > 0 && (
        <SFXTrack scenes={scenes} sfxPaths={sfx_paths} />
      )}

      {/* TTS narration audio */}
      {audio_path ? (
        <Audio src={staticFile(audio_path)} volume={1.0} />
      ) : null}

      {/* Background music */}
      {bgm_path ? (
        <Audio
          src={staticFile(bgm_path)}
          volume={bgm_volume}
          loop
          endAt={durationInFrames}
        />
      ) : null}
    </AbsoluteFill>
  );
};
