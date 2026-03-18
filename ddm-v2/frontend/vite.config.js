import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, '../src/ddm_v2/static/frontend-build'),
    emptyOutDir: true,
    assetsDir: '',
    cssCodeSplit: false,
    rollupOptions: {
      input: path.resolve(__dirname, 'src/main.jsx'),
      output: {
        entryFileNames: 'app.js',
        assetFileNames: 'app.css',
        chunkFileNames: 'chunks/[name].js',
      },
    },
  },
});
