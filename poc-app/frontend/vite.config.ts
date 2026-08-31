import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: true, // bind IPv4 + IPv6 — avoids localhost/127.0.0.1 resolution mismatches
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
