import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',  // Static export for Railway
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },
};

export default nextConfig;
