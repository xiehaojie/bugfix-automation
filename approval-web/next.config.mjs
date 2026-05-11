const apiUrl = process.env.BUGFIX_API_URL || "http://127.0.0.1:8766";

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
