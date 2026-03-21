import React from "react";
import { Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { SceneInfo } from "../types";

interface SfxEvent {
  sceneIndex: number;
  startFrame: number;
  sfxPath: string;
  volume: number;
}

interface SFXTrackProps {
  scenes: SceneInfo[];
  /** Staged SFX paths: { whoosh: "render_id/whoosh.mp3", pop: "...", ding: "..." } */
  sfxPaths: Record<string, string>;
}

/**
 * SFX audio track — plays a short sound effect at the start of each scene.
 *
 * Scene-type mapping:
 *   hook       → pop  (punchy attention-grab)
 *   cta        → ding (reward / call to action)
 *   all others → whoosh (smooth transition)
 *
 * Each SFX is wrapped in a Remotion <Sequence> so it fires at the exact
 * frame corresponding to that scene's start time.
 */
export const SFXTrack: React.FC<SFXTrackProps> = ({ scenes, sfxPaths }) => {
  const { fps } = useVideoConfig();

  if (!sfxPaths || Object.keys(sfxPaths).length === 0) return null;

  const events: SfxEvent[] = scenes.map((scene, idx) => {
    let sfxKey = "whoosh";
    if (scene.scene_type === "hook") sfxKey = "pop";
    if (scene.scene_type === "cta") sfxKey = "ding";

    const sfxPath = sfxPaths[sfxKey] ?? sfxPaths["whoosh"] ?? "";
    const volume = scene.scene_type === "hook" ? 0.55 : 0.3;

    return {
      sceneIndex: idx,
      startFrame: Math.round(scene.start_time * fps),
      sfxPath,
      volume,
    };
  }).filter((e) => e.sfxPath !== "");

  return (
    <>
      {events.map((event) => (
        <Sequence
          key={`sfx-${event.sceneIndex}`}
          from={event.startFrame}
          durationInFrames={Math.round(fps * 1.0)} // max 1s playback window
          layout="none"
        >
          <Audio
            src={staticFile(event.sfxPath)}
            startFrom={0}
            volume={event.volume}
          />
        </Sequence>
      ))}
    </>
  );
};
