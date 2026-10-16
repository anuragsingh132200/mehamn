import type { NextConfig } from 'next';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants';

export default function config(phase: string): NextConfig {
  return {
    output: 'standalone',
    // Keep development compilation from replacing a running production build.
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? '.next-dev' : '.next',
    poweredByHeader: false,
    // Vercel routes the API to the FastAPI service on the same domain.
    ...(process.env.VERCEL === '1' ? {
      env: { NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? '' },
    } : {}),
    experimental: { cpus: 2 },
  };
}
