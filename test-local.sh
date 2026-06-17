#!/bin/bash

# 本地测试脚本 - 在部署前验证应用是否正常工作

set -e

echo "🔍 Re-Life 本地测试脚本"
echo "========================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 已安装"
        return 0
    else
        echo -e "${RED}✗${NC} $1 未安装"
        return 1
    fi
}

# 测试 HTTP 端点
test_endpoint() {
    local url=$1
    local name=$2

    if curl -s -f -o /dev/null "$url"; then
        echo -e "${GREEN}✓${NC} $name 可访问: $url"
        return 0
    else
        echo -e "${RED}✗${NC} $name 不可访问: $url"
        return 1
    fi
}

# 1. 检查依赖
echo "1️⃣  检查依赖..."
check_command node
check_command python3
check_command npm
check_command pip
echo ""

# 2. 检查后端
echo "2️⃣  检查后端..."
if [ ! -d "backend" ]; then
    echo -e "${RED}✗${NC} backend 目录不存在"
    exit 1
fi

cd backend
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗${NC} requirements.txt 不存在"
    exit 1
fi
echo -e "${GREEN}✓${NC} 后端目录结构正确"

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠${NC} .env 文件不存在，使用默认配置"
else
    echo -e "${GREEN}✓${NC} .env 文件存在"
fi

# 启动后端
echo "启动后端服务器..."
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate
pip install -r requirements.txt > /dev/null 2>&1

# 后台启动后端
python main.py &
BACKEND_PID=$!
echo -e "${GREEN}✓${NC} 后端已启动 (PID: $BACKEND_PID)"

cd ..
echo ""

# 3. 检查前端
echo "3️⃣  检查前端..."
if [ ! -d "frontend" ]; then
    echo -e "${RED}✗${NC} frontend 目录不存在"
    kill $BACKEND_PID
    exit 1
fi

cd frontend
if [ ! -f "package.json" ]; then
    echo -e "${RED}✗${NC} package.json 不存在"
    kill $BACKEND_PID
    exit 1
fi
echo -e "${GREEN}✓${NC} 前端目录结构正确"

# 安装依赖
echo "安装前端依赖..."
npm install > /dev/null 2>&1
echo -e "${GREEN}✓${NC} 前端依赖已安装"

# 启动前端
echo "启动前端服务器..."
npm run dev &
FRONTEND_PID=$!
echo -e "${GREEN}✓${NC} 前端已启动 (PID: $FRONTEND_PID)"

cd ..
echo ""

# 4. 等待服务启动
echo "4️⃣  等待服务启动..."
sleep 5
echo ""

# 5. 测试端点
echo "5️⃣  测试服务端点..."
test_endpoint "http://localhost:8000/api/health" "后端健康检查"
test_endpoint "http://localhost:5173" "前端页面"
echo ""

# 6. 测试构建
echo "6️⃣  测试前端构建..."
cd frontend
npm run build > /dev/null 2>&1
if [ -d "dist" ]; then
    SIZE=$(du -sh dist | cut -f1)
    echo -e "${GREEN}✓${NC} 构建成功，产物大小: $SIZE"
else
    echo -e "${RED}✗${NC} 构建失败"
fi
cd ..
echo ""

# 7. 清理
echo "7️⃣  清理测试进程..."
kill $BACKEND_PID 2>/dev/null || true
kill $FRONTEND_PID 2>/dev/null || true
echo -e "${GREEN}✓${NC} 清理完成"
echo ""

# 总结
echo "========================"
echo -e "${GREEN}✅ 本地测试完成！${NC}"
echo ""
echo "下一步："
echo "1. 检查控制台是否有错误"
echo "2. 访问 http://localhost:5173 测试功能"
echo "3. 准备好后运行部署脚本"
echo ""
echo "部署命令:"
echo "  Windows: cd frontend && deploy-cloudflare.bat"
echo "  Mac/Linux: cd frontend && ./deploy-cloudflare.sh"
