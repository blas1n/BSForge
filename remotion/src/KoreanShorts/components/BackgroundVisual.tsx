import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { CameraMovement, TransitionType, VisualAsset } from "../types";

interface BackgroundVisualProps {
  visuals: VisualAsset[];
  enableKenBurns: boolean;
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
 * Native <video> element that syncs to the current frame without delayRender.
 * Remotion's <Video> component calls delayRender() internally which causes
 * 28s timeouts when Chromium can't decode the video codec (VP9, AV1, etc.).
 * This component silently fails on unsupported codecs.
 */
const NativeVideo: React.FC<{
  src: string;
  style: React.CSSProperties;
  onError: () => void;
  currentTimeSec: number;
}> = ({ src, style, onError, currentTimeSec }) => {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && el.readyState >= 1) {
      el.currentTime = currentTimeSec;
    }
  }, [currentTimeSec]);

  return (
    <video
      ref={ref}
      src={src}
      style={style}
      muted
      playsInline
      onError={onError}
    />
  );
};

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
  const [hasError, setHasError] = useState(false);
  const handleError = useCallback(() => setHasError(true), []);

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

  const mediaStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "cover" as const,
    ...cameraStyle,
  };

  if (hasError) {
    return <AbsoluteFill style={{ backgroundColor: "#111111" }} />;
  }

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
        <NativeVideo
          src={staticFile(asset.path)}
          style={mediaStyle}
          onError={handleError}
          currentTimeSec={frameOffset / fps}
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

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000", overflow: "hidden" }}>
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
