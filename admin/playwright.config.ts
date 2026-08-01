import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:15174', trace: 'retain-on-failure' },
  webServer: [
    {
      command: '../backend/.venv/bin/python -m uvicorn app.admin_main:app --host 127.0.0.1 --port 18001',
      cwd: '../backend',
      env: { ...process.env, PYTHONPATH: '.' },
      url: 'http://127.0.0.1:18001/admin-health',
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 15174',
      cwd: '.',
      env: { ...process.env, LORD_TAIL_ADMIN_API_TARGET: 'http://127.0.0.1:18001' },
      url: 'http://127.0.0.1:15174',
      reuseExistingServer: false,
    },
  ],
})
