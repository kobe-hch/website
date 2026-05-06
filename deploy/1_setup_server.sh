#!/bin/bash
# 在服务器上以 root 身份执行一次
# 用法：bash /opt/zhishu/网页展示/deploy/1_setup_server.sh
set -e

export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8

echo "=== [1/5] 系统更新 & 安装基础包 ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv nginx language-pack-zh-hans

locale-gen zh_CN.UTF-8
update-locale LANG=zh_CN.UTF-8

echo "=== [2/5] 创建 Python 虚拟环境 ==="
python3 -m venv /opt/zhishu/venv
echo "虚拟环境创建完成"

echo "=== [3/5] 安装 Python 依赖 ==="
/opt/zhishu/venv/bin/pip install --upgrade pip
/opt/zhishu/venv/bin/pip install -r /opt/zhishu/网页展示/requirements.txt
echo "依赖安装完成"

echo "=== [4/5] 配置 Nginx ==="
cp /opt/zhishu/网页展示/deploy/nginx_huangchanghao.conf /etc/nginx/sites-available/huangchanghao.xin
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/huangchanghao.xin /etc/nginx/sites-enabled/huangchanghao.xin
nginx -t
systemctl enable nginx
systemctl restart nginx
echo "Nginx 配置完成"

echo "=== [5/5] 注册并启动 systemd 服务 ==="
cp /opt/zhishu/网页展示/deploy/zhishu.service /etc/systemd/system/zhishu.service
systemctl daemon-reload
systemctl enable zhishu
systemctl start zhishu
sleep 3

echo ""
echo "============================================"
echo " 部署完成！"
echo " 服务状态："
systemctl status zhishu --no-pager -l
echo "============================================"
echo " 访问地址：http://huangchanghao.xin"
echo "============================================"
