import { Config } from "@remotion/cli/config";

// Output settings for YouTube Shorts (1080x1920, H.264)
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(90);
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
// Bitrate is set via CLI (--video-bitrate 8M) in remotion_compositor.py.
// CRF and videoBitrate are mutually exclusive in Remotion 4+.
