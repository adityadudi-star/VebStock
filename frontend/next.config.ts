import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Public backend address. The NEXT_PUBLIC_API_BASE_URL setting in Vercel overrides it; this default keeps the
  // deployed site connected if that setting is missing at build time.
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || (process.env.NODE_ENV === "production" ? "https://vebstock-api.onrender.com" : ""),
  },
  poweredByHeader: false,
  images: { remotePatterns: [{ protocol: "https", hostname: "images.unsplash.com" }] },
};

export default nextConfig;
