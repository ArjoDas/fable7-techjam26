import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Vercel's adapter handles packaging; standalone output is for self-hosting.
  output: process.env.VERCEL === "1" ? undefined : "standalone",
};

export default nextConfig;

