import type { NextConfig } from "next";

// Static export, served by FastAPI at / (`make ui` builds it to out/).
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
