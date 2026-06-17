@echo off
REM Cloudflare Pages 部署脚本 (Windows)
REM 使用方法: deploy-cloudflare.bat

echo 🚀 开始部署到 Cloudflare Pages...

REM 检查是否在 frontend 目录
if not exist "package.json" (
    echo ❌ 错误: 请在 frontend 目录下运行此脚本
    exit /b 1
)

REM 检查 wrangler 是否安装
where wrangler >nul 2>nul
if %errorlevel% neq 0 (
    echo 📦 Wrangler 未安装，正在安装...
    npm install -g wrangler
)

REM 检查环境变量文件
if not exist ".env.production" (
    echo ⚠️  警告: .env.production 不存在
    echo 请复制 .env.production.template 并填入实际值
    set /p CONTINUE="是否继续? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

REM 安装依赖
echo 📦 安装依赖...
call npm install

REM 构建项目
echo 🔨 构建项目...
call npm run build

REM 检查构建产物
if not exist "dist" (
    echo ❌ 构建失败: dist 目录不存在
    exit /b 1
)

echo ✅ 构建成功！

REM 询问项目名称
set /p PROJECT_NAME="请输入 Cloudflare Pages 项目名称 (默认: relife-app): "
if "%PROJECT_NAME%"=="" set PROJECT_NAME=relife-app

REM 部署到 Cloudflare Pages
echo 🚀 部署到 Cloudflare Pages...
wrangler pages deploy dist --project-name=%PROJECT_NAME%

echo ✅ 部署完成！
echo 🌐 访问 https://%PROJECT_NAME%.pages.dev

pause
