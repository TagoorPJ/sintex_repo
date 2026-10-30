import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = { ...process.env, ...loadEnv(mode, process.cwd(), ''), ...loadEnv(mode, '..', '') };
  const backend = env.VITE_BACKEND_URL || env.PUBLIC_BASE_URL || 'http://127.0.0.1:8010';

  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: {
      port: 5173,
      // only for VITE_STORAGE=api. same origin so we can sample images on a canvas
      proxy: {
        '/api': {
          target: backend,
          changeOrigin: true,
        },
        '/media': {
          target: backend,
          changeOrigin: true,
        },
      },
    },
  };
});
