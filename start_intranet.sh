#!/usr/bin/env bash
# 在项目根目录启动 Streamlit，监听 0.0.0.0，供内网其他机器访问。
# 用法：chmod +x 网页展示/start_intranet.sh && ./网页展示/start_intranet.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "正在启动（内网服务）: http://0.0.0.0:8501"
echo "本机可访问: http://localhost:8501"
echo "内网其他机器请使用: http://<本机内网IP>:8501 或内网 DNS"
echo "按 Ctrl+C 停止"
echo ""

exec streamlit run "网页展示/app.py" \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true
