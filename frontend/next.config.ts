import type { NextConfig } from 'next';
import { PHASE_DEVELOPMENT_SERVER } from 'next/constants';

export default function config(phase: string): NextConfig {
  return {
    output: 'standalone',
    // Keep development compilation from replacing a running production build.
    distDir: phase === PHASE_DEVELOPMENT_SERVER ? '.next-dev' : '.next',
    poweredByHeader: false,
    experimental: { cpus: 2 },
  };
}
