# 竞赛雷达 ContestRadar —— 单容器镜像（后端 API + 前端产物 + Playwright Chromium）
# 构建：docker build -t contest-radar .
# 运行：见 docker-compose.yml（推荐）或
#       docker run -p 8300:8300 -v cr-data:/app/backend/data contest-radar

# 基础镜像仓库可覆盖：海外环境用 --build-arg BASE_REGISTRY=registry-1.docker.io
ARG BASE_REGISTRY=docker.m.daocloud.io
FROM ${BASE_REGISTRY}/library/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# 换国内 apt 源（debian）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# 系统依赖：curl（CCF 源 WAF 兜底需要）+ 中文字体（页面渲染保真）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl fonts-noto-cjk tzdata \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（版本全部锁死，与 requirements.txt 一致）
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Chromium 内核（约150MB，走 npmmirror 镜像；版本随 playwright 1.60.0 锁定）
RUN playwright install --with-deps chromium

# 应用代码 + 前端构建产物（dist 已入库，无需 Node 环境）
COPY backend /app/backend
COPY frontend/dist /app/frontend/dist

# 运行时数据放卷（SQLite）；config.yaml 由 compose 挂载（含 API Key，绝不进镜像）
VOLUME ["/app/backend/data"]

ENV DISABLE_AUTO_OPEN=1
EXPOSE 8300

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8300", "--app-dir", "backend"]
