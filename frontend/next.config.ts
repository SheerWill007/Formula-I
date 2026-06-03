import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Removed ignoreDuringBuilds and ignoreBuildErrors to catch errors during build
  // This ensures type safety and code quality
  images: {
    qualities: [75, 90],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
    ],
  },
}

export default nextConfig
