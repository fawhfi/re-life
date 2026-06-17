@echo off
REM 一键完整部署脚本 - Windows 版本
REM 自动化整个部署流程

echo 🚀 Re-Life 一键部署到 Cloudflare
echo ==================================
echo.

REM 检查必要工具
echo 📋 检查必要工具...
where node >nul 2>nul || (echo ✗ Node.js 未安装 && exit /b 1)
where npm >nul 2>nul || (echo ✗ npm 未安装 && exit /b 1)
where curl >nul 2>nul || (echo ✗ curl 未安装 && exit /b 1)
echo ✓ 所有必要工具已安装
echo.

REM 询问配置
echo 📝 配置信息
echo ----------
set /p FRONTEND_NAME="前端项目名称 [relife-app]: "
if "%FRONTEND_NAME%"=="" set FRONTEND_NAME=relife-app

set /p BACKEND_URL="后端 URL (留空稍后配置): "

set /p HAS_ENV="是否已配置 .env.production? (y/n) [n]: "
if "%HAS_ENV%"=="" set HAS_ENV=n

if /i not "%HAS_ENV%"=="y" (
    echo ⚠ 请先配置 frontend\.env.production
    echo   copy frontend\.env.production.template frontend\.env.production
    echo   然后编辑填入实际值
    pause
)

echo.

REM 检查 Wrangler
echo 🔧 检查 Wrangler CLI...
where wrangler >nul 2>nul
if %errorlevel% neq 0 (
    echo 安装 Wrangler...
    npm install -g wrangler
)
echo ✓ Wrangler 已就绪
echo.

REM 登录 Cloudflare
echo 🔐 登录 Cloudflare...
wrangler whoami >nul 2>nul || wrangler login
echo ✓ 已登录 Cloudflare
echo.

REM 进入前端目录
cd frontend

REM 安装依赖
echo 📦 安装前端依赖...
call npm install
echo ✓ 依赖已安装
echo.

REM 构建
echo 🔨 构建前端...
call npm run build

if not exist "dist" (
    echo ✗ 构建失败
    exit /b 1
)

echo ✓ 构建成功
echo.

REM 部署到 Cloudflare Pages
echo 🚀 部署到 Cloudflare Pages...
wrangler pages deploy dist --project-name=%FRONTEND_NAME%

set DEPLOY_URL=https://%FRONTEND_NAME%.pages.dev
echo.
echo ✅ 前端部署成功！
echo    URL: %DEPLOY_URL%
echo.

REM 后续步骤提示
echo 📋 后续步骤:
echo ----------
echo.
echo 1️⃣  部署后端到 Railway:
echo    cd ..\backend
echo    npm install -g @railway/cli
echo    railway login
echo    railway init
echo    railway up
echo.
echo 2️⃣  配置后端环境变量 (Railway Dashboard):
echo    FIREBASE_API_KEY=your_key
echo    FIREBASE_DATABASE_URL=your_url
echo    NVIDIA_API=your_key
echo    CORS_ORIGINS=%DEPLOY_URL%
echo    ENVIRONMENT=production
echo.
echo 3️⃣  在 Cloudflare Pages 配置环境变量:
echo    访问: https://dash.cloudflare.com
echo    Pages → %FRONTEND_NAME% → Settings → Environment variables
echo    添加所有 VITE_* 变量
echo.
echo 4️⃣  验证部署:
echo    curl https://your-backend.railway.app/api/health
echo    访问 %DEPLOY_URL%
echo.
echo 🎉 部署完成！
echo.
echo 📚 查看完整文档: README_DEPLOYMENT.md
echo.
pause
