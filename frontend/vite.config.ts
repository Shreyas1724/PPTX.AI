import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

const proxy = {'/api': {target: 'http://localhost:8000', ws: true}};
export default defineConfig({
 plugins: [react()],
 resolve: {alias: {'@': new URL('./src', import.meta.url).pathname}},
 server: {proxy},
 preview: {proxy},
});
