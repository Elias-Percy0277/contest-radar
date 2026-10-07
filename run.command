#!/bin/bash
# macOS 启动脚本：双击运行（首次自动建 venv、装依赖、下载 Chromium）
cd "$(dirname "$0")"
PY=python3
command -v $PY >/dev/null 2>&1 || { echo "[ERROR] 未找到 python3，请先安装 Python 3.11+"; exit 1; }

if [ ! -x ".venv/bin/python" ]; then
  echo "[Setup] 创建虚拟环境 .venv ..."
  $PY -m venv .venv
  .venv/bin/python -m pip install --upgrade pip -q
  echo "[Setup] 安装依赖（仅首次，需几分钟）..."
  .venv/bin/python -m pip install -r backend/requirements.txt -q
  echo "[Setup] 下载 Playwright Chromium 内核（约150MB，仅首次）..."
  export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}"
  .venv/bin/python -m playwright install chromium || echo "[Warn] Chromium 下载失败，华为云源将报错，其余源不受影响"
fi

[ -f backend/config.yaml ] || cp backend/config.example.yaml backend/config.yaml

echo "[Start] ContestRadar 启动于 http://127.0.0.1:8300 （浏览器将自动打开）"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8300 --app-dir backend
