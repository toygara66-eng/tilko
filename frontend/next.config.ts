import type { NextConfig } from "next";

const isVercel = Boolean(process.env.VERCEL);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
  ...(!isVercel ? { output: "export" as const } : {}),
};

export default nextConfig;
