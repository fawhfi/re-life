#!/bin/bash

# 一键完整部署脚本 - 自动化整个部署流程
# 适用于 Mac/Linux

set -e

echo "🚀 Re-Life 一键部署到 Cloudflare"
echo "=================================="
echo ""

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 检查必要工具
echo "📋 检查必要工具..."
for cmd in node npm curl; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}✗ $cmd 未安装${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ 所有必要工具已安装${NC}\n"

# 询问配置
echo "📝 配置信息"
echo "----------"

read -p "前端项目名称 [relife-app]: " FRONTEND_NAME
FRONTEND_NAME=${FRONTEND_NAME:-relife-app}

read -p "后端 URL (留空稍后配置): " BACKEND_URL

read -p "是否已配置 .env.production? (y/n) [n]: " HAS_ENV
HAS_ENV=${HAS_ENV:-n}

if [[ $HAS_ENV != "y" ]]; then
    echo -e "${YELLOW}⚠ 请先配置 frontend/.env.production${NC}"
    echo "  cp frontend/.env.production.template frontend/.env.production"
    echo "  然后编辑填入实际值"
    read -p "按 Enter 继续，Ctrl+C 取消..."
fi

echo ""

# 检查 Wrangler
echo "🔧 检查 Wrangler CLI..."
if ! command -v wrangler &> /dev/null; then
    echo "安装 Wrangler..."
    npm install -g wrangler
fi
echo -e "${GREEN}✓ Wrangler 已就绪${NC}\n"

# 登录 Cloudflare
echo "🔐 登录 Cloudflare..."
wrangler whoami &> /dev/null || wrangler login
echo -e "${GREEN}✓ 已登录 Cloudflare${NC}\n"

# 进入前端目录
cd frontend

# 安装依赖
echo "📦 安装前端依赖..."
npm install
echo -e "${GREEN}✓ 依赖已安装${NC}\n"

# 构建
echo "🔨 构建前端..."
npm run build

if [ ! -d "dist" ]; then
    echo -e "${RED}✗ 构建失败${NC}"
    exit 1
fi

BUILD_SIZE=$(du -sh dist | cut -f1)
echo -e "${GREEN}✓ 构建成功 (大小: $BUILD_SIZE)${NC}\n"

# 部署到 Cloudflare Pages
echo "🚀 部署到 Cloudflare Pages..."
wrangler pages deploy dist --project-name="$FRONTEND_NAME"

DEPLOY_URL="https://$FRONTEND_NAME.pages.dev"
echo ""
echo -e "${GREEN}✅ 前端部署成功！${NC}"
echo -e "   URL: ${GREEN}$DEPLOY_URL${NC}"
echo ""

# 后续步骤提示
echo "📋 后续步骤:"
echo "----------"
echo ""
echo "1️⃣  部署后端到 Railway:"
echo "   cd ../backend"
echo "   npm install -g @railway/cli"
echo "   railway login"
echo "   railway init"
echo "   railway up"
echo ""
echo "2️⃣  配置后端环境变量 (Railway Dashboard):"
echo "   FIREBASE_API_KEY=your_key"
echo "   FIREBASE_DATABASE_URL=your_url"
echo "   NVIDIA_API=your_key"
echo "   CORS_ORIGINS=$DEPLOY_URL"
echo "   ENVIRONMENT=production"
echo ""
echo "3️⃣  在 Cloudflare Pages 配置环境变量:"
echo "   访问: https://dash.cloudflare.com"
echo "   Pages → $FRONTEND_NAME → Settings → Environment variables"
echo "   添加所有 VITE_* 变量"
echo ""
echo "4️⃣  验证部署:"
echo "   curl https://your-backend.railway.app/api/health"
echo "   访问 $DEPLOY_URL"
echo ""
echo -e "${GREEN}🎉 部署完成！${NC}"
echo ""
echo "📚 查看完整文档: README_DEPLOYMENT.md"
