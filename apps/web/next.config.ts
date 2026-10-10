import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Phone testing goes through an HTTPS quick tunnel (see README); allow its host in dev.
  allowedDevOrigins: ["*.trycloudflare.com"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
