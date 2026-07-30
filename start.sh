#!/usr/bin/env bash
# 一键启动 Lord Tail 的 API 与前端开发服务器。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-/Users/ray/GD/hermes-agent}"
HERMES_HOME_DIR="${HERMES_HOME:-/Users/ray/.hermes}"
HERMES_BIN="${HERMES_BIN:-$(command -v hermes 2>/dev/null || true)}"
HERMES_BIN="${HERMES_BIN:-/Users/ray/.local/bin/hermes}"

command -v python3 >/dev/null || { echo "未找到 python3。请先安装 Python 3.11+。" >&2; exit 1; }
command -v npm >/dev/null || { echo "未找到 npm。请先安装 Node.js 20+。" >&2; exit 1; }
command -v curl >/dev/null || { echo "未找到 curl。请先安装 curl。" >&2; exit 1; }

cleanup() {
  [[ -n "${LORD_TAIL_CLEANED_UP:-}" ]] && return 0
  LORD_TAIL_CLEANED_UP=1
  echo
  echo "正在停止 Lord Tail 服务…"
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  if [[ -n "${HERMES_GATEWAY_STARTED_BY_SCRIPT_PID:-}" ]]; then
    echo "正在停止本次启动的 Lord Tail Hermes Gateway…"
    kill "$HERMES_GATEWAY_STARTED_BY_SCRIPT_PID" 2>/dev/null || true
  fi
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

load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

load_env_file "$HERMES_AGENT_DIR/.env.wam"
load_env_file "$HERMES_AGENT_DIR/.env"

export HERMES_AGENT_PROFILE="${HERMES_AGENT_PROFILE:-lord-tail-ollama-gemma4-31b}"
load_env_file "$HERMES_HOME_DIR/profiles/$HERMES_AGENT_PROFILE/.env"

detect_listen_pid() {
  local port="$1"
  command -v lsof >/dev/null || return 0
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

read_process_env_var() {
  local pid="$1"
  local name="$2"
  [[ -n "$pid" ]] || return 0
  ps eww -p "$pid" 2>/dev/null | tr ' ' '\n' | awk -F= -v name="$name" '$1 == name {sub(/^[^=]+=/, ""); print; exit}' || true
}

parse_port_from_url() {
  local url="$1"
  python3 - "$url" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
if parsed.port:
    print(parsed.port)
elif parsed.scheme == "https":
    print(443)
elif parsed.scheme == "http":
    print(80)
PY
}

hermes_has_lord_tail_skill() {
  local base_url="$1"
  local api_key="$2"
  local body
  local auth_args=()
  [[ -n "$api_key" ]] && auth_args=(-H "Authorization: Bearer $api_key")
  body="$(curl -fsS "${auth_args[@]}" "$base_url/v1/skills" 2>/dev/null || true)"
  [[ -n "$body" ]] || return 1
  LORD_TAIL_SKILLS_BODY="$body" python3 - <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ.get("LORD_TAIL_SKILLS_BODY", ""))
except Exception:
    sys.exit(1)

skills = data.get("data", [])
names = {item.get("name") for item in skills if isinstance(item, dict)}
required = {"lord-tail-game", "lord-tail-council"}
sys.exit(0 if required <= names else 1)
PY
}

wait_for_lord_tail_hermes() {
  local base_url="$1"
  local api_key="$2"
  local attempts="${3:-45}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if hermes_has_lord_tail_skill "$base_url" "$api_key"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_lord_tail_hermes_gateway() {
  if [[ ! -x "$HERMES_BIN" ]]; then
    echo "未找到可执行 Hermes：$HERMES_BIN" >&2
    echo "可通过 HERMES_BIN=/path/to/hermes 指定。" >&2
    exit 1
  fi

  local log_file="$PROJECT_DIR/.lord-tail-hermes-gateway.log"
  echo "Lord Tail Hermes Gateway 未启动，正在启动 profile：$HERMES_AGENT_PROFILE"
  echo "Hermes Gateway 日志：$log_file"
  (
    cd "$PROJECT_DIR"
    export HERMES_HOME="$HERMES_HOME_DIR"
    export API_SERVER_PORT="$HERMES_RUNS_PORT"
    export API_SERVER_KEY="$HERMES_RUNS_API_KEY"
    export API_SERVER_MODEL_NAME="$HERMES_RUNS_MODEL"
    export HERMES_APPROVAL_POLICY="$HERMES_APPROVAL_POLICY"
    exec "$HERMES_BIN" -p "$HERMES_AGENT_PROFILE" gateway run
  ) >"$log_file" 2>&1 &
  HERMES_GATEWAY_STARTED_BY_SCRIPT_PID=$!
}

select_or_start_lord_tail_hermes() {
  local configured_port="$HERMES_RUNS_PORT"
  local fallback_port="${LORD_TAIL_HERMES_PORT:-8643}"
  local ports=("$configured_port")
  [[ "$fallback_port" != "$configured_port" ]] && ports+=("$fallback_port")

  local port pid detected_key check_key base_url
  for port in "${ports[@]}"; do
    base_url="http://127.0.0.1:$port"
    pid="$(detect_listen_pid "$port")"
    detected_key="$(read_process_env_var "$pid" "API_SERVER_KEY")"
    check_key="$HERMES_RUNS_API_KEY"
    if [[ -n "$pid" ]] && hermes_has_lord_tail_skill "$base_url" "$check_key"; then
      HERMES_RUNS_PORT="$port"
      HERMES_RUNS_BASE_URL="$base_url"
      export HERMES_RUNS_PORT HERMES_RUNS_BASE_URL HERMES_RUNS_API_KEY
      echo "检测到已启动的 Lord Tail Hermes Gateway：$HERMES_RUNS_BASE_URL"
      return 0
    fi
    if [[ -n "$pid" && -n "$detected_key" && "$detected_key" != "$check_key" ]] && hermes_has_lord_tail_skill "$base_url" "$detected_key"; then
      check_key="$detected_key"
      HERMES_RUNS_PORT="$port"
      HERMES_RUNS_BASE_URL="$base_url"
      HERMES_RUNS_API_KEY="$check_key"
      export HERMES_RUNS_PORT HERMES_RUNS_BASE_URL HERMES_RUNS_API_KEY
      echo "检测到已启动的 Lord Tail Hermes Gateway：$HERMES_RUNS_BASE_URL"
      return 0
    fi
  done

  if [[ -n "$(detect_listen_pid "$configured_port")" && "$configured_port" != "$fallback_port" && -z "$(detect_listen_pid "$fallback_port")" ]]; then
    echo "端口 $configured_port 已被非 Lord Tail Hermes Gateway 占用，改用 Lord Tail 专属端口 $fallback_port。"
    HERMES_RUNS_PORT="$fallback_port"
    HERMES_RUNS_BASE_URL="http://127.0.0.1:$HERMES_RUNS_PORT"
    export HERMES_RUNS_PORT HERMES_RUNS_BASE_URL
  elif [[ -n "$(detect_listen_pid "$HERMES_RUNS_PORT")" ]]; then
    echo "端口 $HERMES_RUNS_PORT 已被占用，但该服务没有加载 lord-tail-game skill。" >&2
    echo "请停止占用该端口的进程，或设置 LORD_TAIL_HERMES_PORT 为可用端口。" >&2
    exit 1
  fi

  start_lord_tail_hermes_gateway
  if ! wait_for_lord_tail_hermes "$HERMES_RUNS_BASE_URL" "$HERMES_RUNS_API_KEY"; then
    echo "Lord Tail Hermes Gateway 启动后未能暴露 lord-tail-game skill。" >&2
    echo "请查看日志：$PROJECT_DIR/.lord-tail-hermes-gateway.log" >&2
    exit 1
  fi
  echo "Lord Tail Hermes Gateway 已就绪：$HERMES_RUNS_BASE_URL"
}

if [[ -n "${HERMES_RUNS_BASE_URL:-}" ]]; then
  HERMES_RUNS_PORT="$(parse_port_from_url "$HERMES_RUNS_BASE_URL")"
else
  HERMES_RUNS_PORT="${LORD_TAIL_HERMES_PORT:-8643}"
  HERMES_RUNS_BASE_URL="http://127.0.0.1:$HERMES_RUNS_PORT"
fi

export HERMES_RUNS_API_KEY="${HERMES_RUNS_API_KEY:-${LORD_TAIL_HERMES_API_KEY:-lord-tail-local-test}}"
export HERMES_RUNS_BASE_URL
export HERMES_RUNS_PORT
export HERMES_RUNS_MODEL="${HERMES_RUNS_MODEL:-deepseek-v4-flash}"
export HERMES_APPROVAL_POLICY="${HERMES_APPROVAL_POLICY:-auto-approve}"
export LORD_TAIL_AGENT_API_BASE_URL="${LORD_TAIL_AGENT_API_BASE_URL:-http://127.0.0.1:8000}"
export HERMES_RUNS_TRUST_ENV="${HERMES_RUNS_TRUST_ENV:-false}"

if [[ -z "$HERMES_RUNS_API_KEY" ]]; then
  echo "警告：HERMES_RUNS_API_KEY 未配置；如 Hermes gateway 需要鉴权，书记官传信会失败。" >&2
  echo "可在 $HERMES_AGENT_DIR/.env.wam 中设置 API_SERVER_KEY，或在启动前 export HERMES_RUNS_API_KEY。" >&2
fi

select_or_start_lord_tail_hermes

echo "Hermes Runs：$HERMES_RUNS_BASE_URL"
echo "Hermes Profile：$HERMES_AGENT_PROFILE"
echo "Hermes Model：$HERMES_RUNS_MODEL"

echo "启动 API：http://localhost:8000"
(cd "$BACKEND_DIR" && exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
API_PID=$!

echo "启动前端：http://localhost:5173"
echo "按 Ctrl+C 可同时停止前后端服务。"
cd "$FRONTEND_DIR"
npm run dev -- --host 127.0.0.1
