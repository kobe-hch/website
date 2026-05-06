@echo off
chcp 65001 >nul
setlocal

REM 在项目根目录启动 Streamlit，监听 0.0.0.0，供内网其他机器通过 IP/内网域名访问。
cd /d "%~dp0.."

echo 正在启动（内网服务）: http://0.0.0.0:8501
echo 本机可访问: http://localhost:8501
echo 内网其他电脑请使用: http://^<本机内网IP^>:8501 或内网 DNS 主机名
echo 按 Ctrl+C 停止服务
echo.

streamlit run "网页展示\app.py" --server.address 0.0.0.0 --server.port 8501 --server.headless true

endlocal
