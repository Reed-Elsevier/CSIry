import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://15.135.72.99:8000"}/:path*`,
      },
    ];
  },
};

export default nextConfig;