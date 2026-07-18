#!/usr/bin/env bash
# 一键启动 Lord Tail 的 API 与前端开发服务器。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"

command -v python3 >/dev/null || { echo "未找到 python3。请先安装 Python 3.11+。" >&2; exit 1; }
command -v npm >/dev/null || { echo "未找到 npm。请先安装 Node.js 20+。" >&2; exit 1; }

cleanup() {
  echo
  echo "正在停止 Lord Tail 服务…"
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "正在创建 Python 虚拟环境…"
  python3 -m venv "$VENV_DIR"
fi

echo "正在确认后端依赖…"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet -r "$BACKEND_DIR/requirements.txt"

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "正在安装前端依赖…"
  (cd "$FRONTEND_DIR" && npm ci)
fi

export HERMES_RUNS_BASE_URL="${HERMES_RUNS_BASE_URL:-http://127.0.0.1:8643}"
export HERMES_RUNS_API_KEY="${HERMES_RUNS_API_KEY:-lord-tail-local-test}"
export HERMES_AGENT_PROFILE="${HERMES_AGENT_PROFILE:-lord-tail-ollama-gemma4-31b}"
export HERMES_RUNS_MODEL="${HERMES_RUNS_MODEL:-deepseek-v4-flash}"
export HERMES_APPROVAL_POLICY="${HERMES_APPROVAL_POLICY:-auto-approve}"
export LORD_TAIL_AGENT_API_BASE_URL="${LORD_TAIL_AGENT_API_BASE_URL:-http://127.0.0.1:8000}"

echo "启动 API：http://localhost:8000"
(cd "$BACKEND_DIR" && exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
API_PID=$!

echo "启动前端：http://localhost:5173"
echo "按 Ctrl+C 可同时停止前后端服务。"
cd "$FRONTEND_DIR"
npm run dev -- --host 127.0.0.1
