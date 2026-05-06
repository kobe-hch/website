@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0.."

start "" cmd /k "cd /d \"%cd%\" && streamlit run \"网页展示/app.py\" --server.port 8501 --server.headless false"
timeout /t 2 >nul
start "" "http://localhost:8501"

endlocal
