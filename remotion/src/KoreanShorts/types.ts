/**
 * Type definitions for Korean Shorts composition props.
 * These mirror the Python data structures passed from RemotionCompositor.
 */

export type CameraMovement =
  | "ken_burns"
  | "pan_left"
  | "pan_right"
  | "tilt_up"
  | "tilt_down"
  | "zoom_out"
  | "static";

export type TextAnimation =
  | "none"
  | "fade_in"
  | "slide_up"
  | "pop"
  | "bounce";

export type TransitionType =
  | "none"
  | "fade"
  | "crossfade"
  | "slide_left"
  | "slide_right"
  | "zoom"
  | "flash"
  | "wipe";

export interface WordSegment {
  word: string;
  start: number; // seconds
  end: number; // seconds
}

export interface SubtitleSegment {
  index: number;
  start: number; // seconds
  end: number; // seconds
  text: string;
  words: WordSegment[] | null; // word-level timestamps for karaoke
  text_animation?: TextAnimation;
}

export interface VisualAsset {
  path: string; // absolute file path
  type: "image" | "video";
  start_time: number; // seconds (offset in final video)
  duration: number; // seconds
  camera_movement?: CameraMovement;
  transition_in?: TransitionType;
  transition_out?: TransitionType;
}

export interface SafeZone {
  top_px: number;
  bottom_px: number;
  left_px: number;
  right_px: number;
}

export interface Theme {
  accent_color: string;
  secondary_color: string;
  font_family: string;
  headline_font_size_line1: number;
  headline_font_size_line2: number;
  subtitle_font_size: number;
  headline_bg_color: string;
  headline_bg_opacity: number;
  highlight_color: string;
  text_color: string;
  outline_color: string;
}

export type SceneType =
  | "hook"
  | "intro"
  | "content"
  | "example"
  | "commentary"
  | "reaction"
  | "conclusion"
  | "cta";

export type VisualStyle = "neutral" | "persona" | "emphasis";

export interface SceneInfo {
  index: number;
  scene_type: SceneType;
  visual_style: VisualStyle;
  transition_in: TransitionType;
  transition_out: TransitionType;
  emphasis_words: string[];
  start_time: number; // seconds
  duration: number; // seconds
}

export interface KoreanShortsProps {
  // Video parameters
  duration_seconds: number;
  fps: number;
  width: number;
  height: number;

  // Audio
  audio_path: string;
  bgm_path: string | null;
  bgm_volume: number;

  // Headline (top area)
  headline_line1: string;
  headline_line2: string;
  accent_color: string; // legacy fallback
  headline_animation?: TextAnimation;

  // Visual assets (background)
  visuals: VisualAsset[];

  // Subtitles
  subtitles: SubtitleSegment[];

  // Effects
  enable_ken_burns: boolean;
  enable_karaoke: boolean;

  // Safe zone
  safe_zone?: SafeZone;

  // Theme
  theme?: Theme;

  // Scene metadata (optional, backwards-compatible)
  scenes?: SceneInfo[];
}
