@echo off
REM 本地测试脚本 - Windows 版本

echo 🔍 Re-Life 本地测试脚本
echo ========================
echo.

REM 1. 检查依赖
echo 1️⃣ 检查依赖...
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo ✗ Node.js 未安装
    exit /b 1
) else (
    echo ✓ Node.js 已安装
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ✗ Python 未安装
    exit /b 1
) else (
    echo ✓ Python 已安装
)

where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo ✗ npm 未安装
    exit /b 1
) else (
    echo ✓ npm 已安装
)

where pip >nul 2>nul
if %errorlevel% neq 0 (
    echo ✗ pip 未安装
    exit /b 1
) else (
    echo ✓ pip 已安装
)
echo.

REM 2. 检查后端
echo 2️⃣ 检查后端...
if not exist "backend" (
    echo ✗ backend 目录不存在
    exit /b 1
)

cd backend
if not exist "requirements.txt" (
    echo ✗ requirements.txt 不存在
    exit /b 1
)
echo ✓ 后端目录结构正确

if not exist ".env" (
    echo ⚠ .env 文件不存在，使用默认配置
) else (
    echo ✓ .env 文件存在
)

REM 创建虚拟环境（如果不存在）
if not exist "venv" (
    echo 创建 Python 虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境并安装依赖
call venv\Scripts\activate.bat
pip install -r requirements.txt >nul 2>&1
echo ✓ 后端依赖已安装

REM 后台启动后端
echo 启动后端服务器...
start /B python main.py
timeout /t 3 >nul
echo ✓ 后端已启动

cd ..
echo.

REM 3. 检查前端
echo 3️⃣ 检查前端...
if not exist "frontend" (
    echo ✗ frontend 目录不存在
    exit /b 1
)

cd frontend
if not exist "package.json" (
    echo ✗ package.json 不存在
    exit /b 1
)
echo ✓ 前端目录结构正确

REM 安装依赖
echo 安装前端依赖...
call npm install >nul 2>&1
echo ✓ 前端依赖已安装

REM 后台启动前端
echo 启动前端服务器...
start /B npm run dev
timeout /t 5 >nul
echo ✓ 前端已启动

cd ..
echo.

REM 4. 测试端点
echo 4️⃣ 测试服务端点...
echo 等待服务启动...
timeout /t 5 >nul

curl -s -f http://localhost:8000/api/health >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ 后端健康检查: http://localhost:8000/api/health
) else (
    echo ✗ 后端不可访问: http://localhost:8000/api/health
)

curl -s -f http://localhost:5173 >nul 2>&1
if %errorlevel% equ 0 (
    echo ✓ 前端页面: http://localhost:5173
) else (
    echo ✗ 前端不可访问: http://localhost:5173
)
echo.

REM 5. 测试构建
echo 5️⃣ 测试前端构建...
cd frontend
call npm run build >nul 2>&1
if exist "dist" (
    echo ✓ 构建成功
) else (
    echo ✗ 构建失败
)
cd ..
echo.

REM 6. 显示结果
echo ========================
echo ✅ 本地测试完成！
echo.
echo 服务正在运行:
echo   - 后端: http://localhost:8000
echo   - 前端: http://localhost:5173
echo.
echo 下一步:
echo 1. 在浏览器访问 http://localhost:5173
echo 2. 测试注册、登录、扫描等功能
echo 3. 准备好后按任意键停止服务
echo.
pause

REM 清理
echo.
echo 停止服务...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
echo ✓ 服务已停止
echo.
echo 部署命令:
echo   cd frontend ^&^& deploy-cloudflare.bat
