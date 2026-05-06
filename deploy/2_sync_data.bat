@echo off
chcp 65001 > nul
setlocal

:: ======================================================
:: 每次更新 parquet 数据后，双击此脚本同步到服务器
:: 使用前：将下面的 SERVER_IP 改为你的服务器真实 IP
:: ======================================================
set SERVER_IP=替换为你的服务器IP
set SERVER_USER=root
set REMOTE_DIR=/opt/zhishu

echo 正在将本地 parquet 数据同步到服务器 %SERVER_IP% ...
echo.

scp "..\指数代码与名称.parquet"  %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/
scp "..\指数价格数据.parquet"    %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/
scp "..\指数PE数据.parquet"      %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/
scp "..\指数PB数据.parquet"      %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/
scp "..\指数PB数据_海外.parquet" %SERVER_USER%@%SERVER_IP%:%REMOTE_DIR%/

echo.
echo 同步完成！服务器数据已更新。
pause
