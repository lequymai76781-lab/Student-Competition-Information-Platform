import path from "node:path";
import { fileURLToPath } from "node:url";

process.env.NEXT_TELEMETRY_DISABLED = "1";

const workspaceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: workspaceRoot
  }
};

export default nextConfig;
