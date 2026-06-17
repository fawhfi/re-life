#!/bin/bash

# Cloudflare Pages 部署脚本
# 使用方法: ./deploy-cloudflare.sh

set -e

echo "🚀 开始部署到 Cloudflare Pages..."

# 检查是否在 frontend 目录
if [ ! -f "package.json" ]; then
    echo "❌ 错误: 请在 frontend 目录下运行此脚本"
    exit 1
fi

# 检查 wrangler 是否安装
if ! command -v wrangler &> /dev/null; then
    echo "📦 Wrangler 未安装，正在安装..."
    npm install -g wrangler
fi

# 检查环境变量文件
if [ ! -f ".env.production" ]; then
    echo "⚠️  警告: .env.production 不存在"
    echo "请复制 .env.production.template 并填入实际值"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 安装依赖
echo "📦 安装依赖..."
npm install

# 构建项目
echo "🔨 构建项目..."
npm run build

# 检查构建产物
if [ ! -d "dist" ]; then
    echo "❌ 构建失败: dist 目录不存在"
    exit 1
fi

echo "✅ 构建成功！"
echo "📊 构建产物大小:"
du -sh dist

# 询问项目名称
read -p "请输入 Cloudflare Pages 项目名称 (默认: relife-app): " PROJECT_NAME
PROJECT_NAME=${PROJECT_NAME:-relife-app}

# 部署到 Cloudflare Pages
echo "🚀 部署到 Cloudflare Pages..."
wrangler pages deploy dist --project-name="$PROJECT_NAME"

echo "✅ 部署完成！"
echo "🌐 访问 https://$PROJECT_NAME.pages.dev"
