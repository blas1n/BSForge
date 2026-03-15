import React from "react";
import { Composition } from "remotion";
import { KoreanShorts } from "./KoreanShorts";
import type { KoreanShortsProps } from "./KoreanShorts/types";

const defaultProps: KoreanShortsProps = {
  duration_seconds: 60,
  fps: 30,
  audio_path: "",
  bgm_path: null,
  bgm_volume: 0.08,
  headline_line1: "이건 진짜 충격적",
  headline_line2: "AI가 인류를 바꾼다",
  accent_color: "#FF69B4",
  visuals: [],
  subtitles: [],
  enable_ken_burns: true,
  enable_karaoke: true,
  scenes: [],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      <Composition
        id="KoreanShorts"
        component={KoreanShorts as any}
        durationInFrames={defaultProps.duration_seconds * defaultProps.fps}
        fps={defaultProps.fps}
        width={1080}
        height={1920}
        defaultProps={defaultProps as any}
        calculateMetadata={async ({ props }: { props: any }) => {
          return {
            durationInFrames: Math.ceil(props.duration_seconds * props.fps),
            fps: props.fps,
            width: 1080,
            height: 1920,
          };
        }}
      />
    </>
  );
};
