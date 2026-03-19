import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CameraMovement, ColorGrading, TransitionType, VisualAsset } from "../types";

interface BackgroundVisualProps {
  visuals: VisualAsset[];
  enableKenBurns: boolean;
  colorGrading?: ColorGrading;
}

interface SingleVisualProps {
  asset: VisualAsset;
  enableKenBurns: boolean;
  frameOffset: number;
  fps: number;
  totalFrames: number; // total frames for this visual's duration
}

// Ken Burns defaults
const KEN_BURNS_ZOOM_SPEED = 0.0003;
const KEN_BURNS_START_SCALE = 1.08;

// Pan/tilt movement range (percentage of image dimension)
const PAN_RANGE = 0.08; // 8% of width/height

// Pattern interrupt: subtle micro-zoom pulse every N seconds to re-capture attention
const INTERRUPT_INTERVAL_SEC = 2.5;
const INTERRUPT_DURATION_FRAMES = 7; // ~0.23s at 30fps — snappy but not jarring

/**
 * Returns a scale multiplier (1.0–1.03) for the pattern-interrupt micro-zoom.
 * Triggers every INTERRUPT_INTERVAL_SEC; smoothly ramps up then back down.
 */
function getPatternInterruptScale(frameOffset: number, fps: number): number {
  const intervalFrames = Math.round(fps * INTERRUPT_INTERVAL_SEC);
  const posInInterval = frameOffset % intervalFrames;
  if (posInInterval >= INTERRUPT_DURATION_FRAMES) return 1.0;
  return interpolate(
    posInInterval,
    [0, Math.floor(INTERRUPT_DURATION_FRAMES / 2), INTERRUPT_DURATION_FRAMES],
    [1.0, 1.03, 1.0],
    { easing: Easing.inOut(Easing.quad), extrapolateRight: "clamp" },
  );
}

/**
 * Calculate camera transform based on movement type.
 */
function getCameraTransform(
  movement: CameraMovement,
  frameOffset: number,
  totalFrames: number,
): React.CSSProperties {
  const progress = totalFrames > 0 ? frameOffset / totalFrames : 0;

  switch (movement) {
    case "ken_burns": {
      // Eased Ken Burns: smooth ease-in-out instead of linear
      const scale = interpolate(progress, [0, 1], [1.0, 1.12], {
        easing: Easing.inOut(Easing.quad),
        extrapolateRight: "clamp",
      });
      return { transform: `scale(${scale})`, transformOrigin: "center center" };
    }
    case "pan_left": {
      const tx = interpolate(progress, [0, 1], [PAN_RANGE * 100, -PAN_RANGE * 100], {
        easing: Easing.inOut(Easing.sin),
      });
      return {
        transform: `scale(1.1) translateX(${tx}%)`,
        transformOrigin: "center center",
      };
    }
    case "pan_right": {
      const tx = interpolate(progress, [0, 1], [-PAN_RANGE * 100, PAN_RANGE * 100], {
        easing: Easing.inOut(Easing.sin),
      });
      return {
        transform: `scale(1.1) translateX(${tx}%)`,
        transformOrigin: "center center",
      };
    }
    case "tilt_up": {
      const ty = interpolate(progress, [0, 1], [PAN_RANGE * 100, -PAN_RANGE * 100], {
        easing: Easing.inOut(Easing.sin),
      });
      return {
        transform: `scale(1.1) translateY(${ty}%)`,
        transformOrigin: "center center",
      };
    }
    case "tilt_down": {
      const ty = interpolate(progress, [0, 1], [-PAN_RANGE * 100, PAN_RANGE * 100], {
        easing: Easing.inOut(Easing.sin),
      });
      return {
        transform: `scale(1.1) translateY(${ty}%)`,
        transformOrigin: "center center",
      };
    }
    case "zoom_out": {
      const scale = interpolate(progress, [0, 1], [1.2, 1.0], {
        easing: Easing.inOut(Easing.quad),
        extrapolateRight: "clamp",
      });
      return { transform: `scale(${scale})`, transformOrigin: "center center" };
    }
    case "static":
    default:
      return { transform: "scale(1)", transformOrigin: "center center" };
  }
}

/**
 * Calculate transition opacity for a visual asset.
 */
function getTransitionOpacity(
  transitionIn: TransitionType | undefined,
  transitionOut: TransitionType | undefined,
  frameOffset: number,
  totalFrames: number,
  fps: number,
): number {
  const transitionDuration = Math.min(Math.round(fps * 0.3), totalFrames / 2); // 0.3s or half duration

  let opacity = 1;

  // Transition in
  if (transitionIn && transitionIn !== "none" && frameOffset < transitionDuration) {
    if (transitionIn === "fade" || transitionIn === "crossfade") {
      opacity = interpolate(frameOffset, [0, transitionDuration], [0, 1], {
        extrapolateRight: "clamp",
      });
    } else if (transitionIn === "flash") {
      // Flash: white overlay fading out
      opacity = interpolate(frameOffset, [0, transitionDuration / 2], [0.3, 1], {
        extrapolateRight: "clamp",
      });
    }
    // slide, zoom, wipe handled via transform
  }

  // Transition out
  const framesRemaining = totalFrames - frameOffset;
  if (
    transitionOut &&
    transitionOut !== "none" &&
    framesRemaining < transitionDuration
  ) {
    if (transitionOut === "fade" || transitionOut === "crossfade") {
      opacity *= interpolate(
        framesRemaining,
        [0, transitionDuration],
        [0, 1],
        { extrapolateRight: "clamp" },
      );
    }
  }

  return opacity;
}

/**
 * Calculate transition transform for slide/zoom effects.
 */
function getTransitionTransform(
  transitionIn: TransitionType | undefined,
  frameOffset: number,
  totalFrames: number,
  fps: number,
): string {
  const transitionDuration = Math.min(Math.round(fps * 0.3), totalFrames / 2);

  if (!transitionIn || transitionIn === "none" || frameOffset >= transitionDuration) {
    return "";
  }

  const progress = interpolate(frameOffset, [0, transitionDuration], [0, 1], {
    extrapolateRight: "clamp",
  });

  switch (transitionIn) {
    case "slide_left": {
      const tx = interpolate(progress, [0, 1], [100, 0]);
      return `translateX(${tx}%)`;
    }
    case "slide_right": {
      const tx = interpolate(progress, [0, 1], [-100, 0]);
      return `translateX(${tx}%)`;
    }
    case "zoom": {
      const scale = interpolate(progress, [0, 1], [1.5, 1.0]);
      return `scale(${scale})`;
    }
    case "wipe": {
      // Wipe via clip-path is handled in the container
      return "";
    }
    default:
      return "";
  }
}


/**
 * Single image/video visual with camera movement and transitions.
 */
const SingleVisual: React.FC<SingleVisualProps> = ({
  asset,
  enableKenBurns,
  frameOffset,
  fps,
  totalFrames,
}) => {
  // Determine camera movement
  const movement: CameraMovement =
    asset.camera_movement ?? (enableKenBurns ? "ken_burns" : "static");
  const cameraStyle = getCameraTransform(movement, frameOffset, totalFrames);

  // Transition effects
  const opacity = getTransitionOpacity(
    asset.transition_in,
    asset.transition_out,
    frameOffset,
    totalFrames,
    fps,
  );
  const transitionTransform = getTransitionTransform(
    asset.transition_in,
    frameOffset,
    totalFrames,
    fps,
  );

  // Wipe transition via clip-path
  const clipPath =
    asset.transition_in === "wipe" && frameOffset < Math.round(fps * 0.3)
      ? `inset(0 ${interpolate(
          frameOffset,
          [0, Math.round(fps * 0.3)],
          [100, 0],
          { extrapolateRight: "clamp" },
        )}% 0 0)`
      : undefined;

  // Combine camera movement transform with pattern-interrupt scale
  const interruptScale = getPatternInterruptScale(frameOffset, fps);
  const existingTransform = cameraStyle.transform ?? "";
  const combinedTransform = existingTransform
    ? `${existingTransform} scale(${interruptScale})`
    : `scale(${interruptScale})`;

  const mediaStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    ...cameraStyle,
    transform: combinedTransform,
  };

  const containerStyle: React.CSSProperties = {
    opacity,
    transform: transitionTransform || undefined,
    clipPath,
    width: "100%",
    height: "100%",
  };

  return (
    <div style={containerStyle}>
      {asset.type === "video" ? (
        <OffthreadVideo
          src={staticFile(asset.path)}
          style={mediaStyle}
          muted
          startFrom={0}
        />
      ) : (
        <Img src={staticFile(asset.path)} style={mediaStyle} />
      )}
    </div>
  );
};

/**
 * Background visual track with camera movements and transitions.
 * Displays visuals in sequence based on their start_time/duration.
 */
export const BackgroundVisual: React.FC<BackgroundVisualProps> = ({
  visuals,
  enableKenBurns,
  colorGrading,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentTimeSec = frame / fps;

  // Find the active visual for the current time
  const activeVisual = visuals.find(
    (v) =>
      currentTimeSec >= v.start_time &&
      currentTimeSec < v.start_time + v.duration,
  );

  if (!activeVisual) {
    return <AbsoluteFill style={{ backgroundColor: "#000000" }} />;
  }

  const frameOffset = (currentTimeSec - activeVisual.start_time) * fps;
  const totalFrames = activeVisual.duration * fps;

  // Flash transition: white overlay
  const showFlash =
    activeVisual.transition_in === "flash" &&
    frameOffset < Math.round(fps * 0.15);
  const flashOpacity = showFlash
    ? interpolate(frameOffset, [0, Math.round(fps * 0.15)], [0.8, 0], {
        extrapolateRight: "clamp",
      })
    : 0;

  // Color grading via CSS filters
  const filterParts: string[] = [];
  if (colorGrading) {
    if (colorGrading.brightness !== 1.0) filterParts.push(`brightness(${colorGrading.brightness})`);
    if (colorGrading.contrast !== 1.0) filterParts.push(`contrast(${colorGrading.contrast})`);
    if (colorGrading.saturation !== 1.0) filterParts.push(`saturate(${colorGrading.saturation})`);
    if (colorGrading.warmth > 0) filterParts.push(`sepia(${colorGrading.warmth})`);
  }
  const cssFilter = filterParts.length > 0 ? filterParts.join(" ") : undefined;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000", overflow: "hidden", filter: cssFilter }}>
      <SingleVisual
        asset={activeVisual}
        enableKenBurns={enableKenBurns}
        frameOffset={frameOffset}
        fps={fps}
        totalFrames={totalFrames}
      />
      {/* Flash overlay */}
      {flashOpacity > 0 && (
        <AbsoluteFill
          style={{
            backgroundColor: "#FFFFFF",
            opacity: flashOpacity,
            pointerEvents: "none",
          }}
        />
      )}
    </AbsoluteFill>
  );
};
