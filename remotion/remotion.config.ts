import { Config } from "@remotion/cli/config";

// Output settings for YouTube Shorts (1080x1920, H.264)
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(90);
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
Config.setCrf(23);
