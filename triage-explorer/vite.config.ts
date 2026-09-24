import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Under Aspire the backend URL is injected via service discovery; standalone it defaults to :8000.
const backend =
  process.env.BACKEND_HTTP ?? process.env.services__backend__http__0 ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // public hostname served through the tap / Cloudflare tunnel
    allowedHosts: ['ai-weeks.p7e.dev'],
    proxy: { '/api': backend },
  },
})
