/**
 * Text animation utilities for Korean Shorts components.
 *
 * Provides reusable animation functions using Remotion's
 * interpolate() and spring() for text entrance effects.
 */

import { interpolate, spring } from "remotion";
import { TextAnimation } from "./types";

/**
 * Calculate CSS properties for a text animation at the given frame.
 *
 * @param animation - Animation type
 * @param frame - Current frame number
 * @param fps - Frames per second
 * @param startFrame - Frame when the element first appears
 * @param durationFrames - Animation duration in frames (default: 10)
 * @returns CSS properties to apply
 */
export function getTextAnimationStyle(
  animation: TextAnimation,
  frame: number,
  fps: number,
  startFrame: number,
  durationFrames: number = 10,
): React.CSSProperties {
  const elapsed = frame - startFrame;

  if (elapsed < 0) {
    return { opacity: 0 };
  }

  switch (animation) {
    case "fade_in": {
      const opacity = interpolate(elapsed, [0, durationFrames], [0, 1], {
        extrapolateRight: "clamp",
      });
      return { opacity };
    }

    case "slide_up": {
      const opacity = interpolate(elapsed, [0, durationFrames], [0, 1], {
        extrapolateRight: "clamp",
      });
      const translateY = interpolate(
        elapsed,
        [0, durationFrames],
        [50, 0],
        { extrapolateRight: "clamp" },
      );
      return { opacity, transform: `translateY(${translateY}px)` };
    }

    case "pop": {
      const scale = spring({
        frame: elapsed,
        fps,
        config: { damping: 12, stiffness: 200, mass: 0.8 },
      });
      return { opacity: Math.min(elapsed / 2, 1), transform: `scale(${scale})` };
    }

    case "bounce": {
      const scale = spring({
        frame: elapsed,
        fps,
        config: { damping: 8, stiffness: 300, mass: 0.6 },
      });
      return { opacity: Math.min(elapsed / 2, 1), transform: `scale(${scale})` };
    }

    case "none":
    default:
      return { opacity: 1 };
  }
}
