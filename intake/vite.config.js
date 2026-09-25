import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: Number(process.env.PORT || 8080),
    strictPort: true,
    proxy: { '/api': process.env.BACKEND_URL || 'http://127.0.0.1:8081' },
  },
});
