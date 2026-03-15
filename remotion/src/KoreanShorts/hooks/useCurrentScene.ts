/**
 * Hook to find the active scene at the current playhead position.
 */

import { useCurrentFrame, useVideoConfig } from "remotion";
import { SceneInfo } from "../types";

/**
 * Returns the SceneInfo whose time range contains the current frame,
 * or null if no scenes are provided or the frame is out of range.
 */
export function useCurrentScene(
  scenes: SceneInfo[] | undefined,
): SceneInfo | null {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!scenes || scenes.length === 0) return null;

  const currentTimeSec = frame / fps;

  return (
    scenes.find(
      (s) =>
        currentTimeSec >= s.start_time &&
        currentTimeSec < s.start_time + s.duration,
    ) ?? null
  );
}
