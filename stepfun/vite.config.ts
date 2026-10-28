import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': process.env.STEPFUN_API || 'http://127.0.0.1:8797',
    },
  },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
  },
  optimizeDeps: {
    exclude: ['@huggingface/transformers'],
  },
});
