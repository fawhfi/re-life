# Cloudflare 部署指南 / Cloudflare Deployment Guide

## 概述 / Overview

本指南介绍如何将 Re-Life React 应用部署到 Cloudflare 平台。

This guide explains how to deploy the Re-Life React application to Cloudflare.

## 架构选择 / Architecture Options

### 选项 1：Cloudflare Pages (推荐前端) + Cloudflare Workers (后端)
- **前端**: Cloudflare Pages 托管静态 React 应用
- **后端**: Cloudflare Workers 运行 API（需要重写为 Workers 兼容）

### 选项 2：Cloudflare Pages (前端) + 外部后端
- **前端**: Cloudflare Pages
- **后端**: Railway / Render / Google Cloud Run / 其他 VPS

### 选项 3：完全使用 Cloudflare Pages + Functions
- 前端和轻量级 API 都在 Cloudflare Pages Functions

---

## 🚀 方案 A：Cloudflare Pages (前端) + 外部后端 (推荐)

这是最简单的方案，因为你的 FastAPI 后端使用了 Python、ONNX 模型等，不适合直接迁移到 Workers。

### 步骤 1: 准备前端构建

#### 1.1 更新 `vite.config.js`

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,  // 生产环境不需要 sourcemap
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          firebase: ['firebase/app', 'firebase/auth', 'firebase/database'],
        }
      }
    }
  }
})
```

#### 1.2 配置环境变量

在 `frontend/` 目录创建 `.env.production`:

```bash
VITE_API_BASE_URL=https://your-backend-api.com
VITE_FIREBASE_API_KEY=your_firebase_key
VITE_FIREBASE_AUTH_DOMAIN=your_app.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://your_app.firebaseio.com
VITE_FIREBASE_PROJECT_ID=your_project_id
```

#### 1.3 更新 API 客户端

修改 `frontend/src/api/client.js`:

```javascript
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  }
})

export default client
```

#### 1.4 构建前端

```bash
cd frontend
npm install
npm run build
```

构建产物在 `frontend/dist/` 目录。

### 步骤 2: 部署到 Cloudflare Pages

#### 方法 A: 通过 Wrangler CLI (推荐)

1. 安装 Wrangler:
```bash
npm install -g wrangler
```

2. 登录 Cloudflare:
```bash
wrangler login
```

3. 部署:
```bash
cd frontend
wrangler pages deploy dist --project-name=relife-app
```

#### 方法 B: 通过 Cloudflare Dashboard (图形界面)

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **Pages** 部分
3. 点击 **Create a project**
4. 选择 **Upload assets**
5. 上传 `frontend/dist/` 文件夹
6. 设置项目名称（如 `relife-app`）
7. 点击 **Deploy**

#### 方法 C: 通过 Git 集成 (自动部署)

1. 将代码推送到 GitHub/GitLab
2. 在 Cloudflare Pages 中选择 **Connect to Git**
3. 选择仓库和分支
4. 配置构建设置:
   - **Build command**: `cd frontend && npm install && npm run build`
   - **Build output directory**: `frontend/dist`
   - **Root directory**: `/`
5. 添加环境变量（见步骤 1.2）
6. 点击 **Save and Deploy**

### 步骤 3: 配置环境变量 (Dashboard)

在 Cloudflare Pages 项目设置中:

1. 进入 **Settings** → **Environment variables**
2. 添加所有 `VITE_*` 变量
3. 保存并重新部署

### 步骤 4: 配置 SPA 路由

创建 `frontend/public/_redirects` 文件:

```
/* /index.html 200
```

或创建 `frontend/public/_headers` 文件（可选，用于安全头）:

```
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
```

重新构建并部署。

### 步骤 5: 部署后端到外部服务

#### 选项 A: Railway (简单快速)

```bash
cd backend
# 创建 railway.json
echo '{"build": {"builder": "nixpacks"}, "deploy": {"startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT"}}' > railway.json

# 安装 Railway CLI
npm install -g @railway/cli

# 登录并部署
railway login
railway init
railway up
```

#### 选项 B: Render (免费额度)

1. 登录 [Render](https://render.com/)
2. 创建新的 **Web Service**
3. 连接 GitHub 仓库
4. 配置:
   - **Build Command**: `cd backend && pip install -r requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3.9+
5. 添加环境变量（从 `.env` 复制）
6. 部署

#### 选项 C: Google Cloud Run

```bash
cd backend

# 创建 Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# 构建并部署
gcloud builds submit --tag gcr.io/YOUR_PROJECT/relife-backend
gcloud run deploy relife-backend --image gcr.io/YOUR_PROJECT/relife-backend --platform managed
```

### 步骤 6: 配置 CORS

更新 `backend/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://relife-app.pages.dev",  # 你的 Cloudflare Pages 域名
        "https://your-custom-domain.com",  # 自定义域名（如有）
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

重新部署后端。

### 步骤 7: 更新前端环境变量

获取后端部署的 URL（如 `https://relife-backend.railway.app`），更新 Cloudflare Pages 的环境变量:

```
VITE_API_BASE_URL=https://relife-backend.railway.app
```

触发重新部署。

---

## 🔧 方案 B：Cloudflare Workers (完全 Cloudflare)

**注意**: 此方案需要将 FastAPI 后端重写为 JavaScript/TypeScript Workers，工作量较大。

### 前端部署（同方案 A）

### 后端迁移到 Workers

由于你的后端使用了：
- Python FastAPI
- ONNX Runtime（机器学习模型）
- 复杂的 AI 提供商集成

**不建议**直接迁移到 Cloudflare Workers，因为：
1. Workers 运行 JavaScript/TypeScript/Rust/C++，不支持 Python
2. Workers 有执行时间限制（CPU 时间 50ms 免费版，30s 付费版）
3. ONNX 模型推理可能超出限制

**替代方案**：
- 使用 Cloudflare Workers 作为轻量级 API 网关
- 将重型计算（AI 分析、CNN 推理）代理到外部后端
- 简单的 API（如获取新闻、奖励）可以用 Workers 实现

---

## 📱 方案 C：Cloudflare Pages Functions (轻量级 API)

适用于不需要机器学习的简单 API。

### 创建 Pages Functions

在 `frontend/functions/` 目录创建 API 端点：

```javascript
// frontend/functions/api/health.js
export async function onRequest(context) {
  return new Response(JSON.stringify({ status: 'ok' }), {
    headers: { 'Content-Type': 'application/json' }
  })
}

// frontend/functions/api/news.js
export async function onRequest(context) {
  const { SERPAPI_KEY } = context.env
  
  // 调用外部新闻 API
  const response = await fetch(`https://serpapi.com/search?api_key=${SERPAPI_KEY}`)
  const data = await response.json()
  
  return new Response(JSON.stringify(data), {
    headers: { 'Content-Type': 'application/json' }
  })
}
```

这些函数会自动部署为 `/api/health` 和 `/api/news` 端点。

对于重型 API（如图像分析），仍需外部后端。

---

## 🌐 自定义域名

### 在 Cloudflare Pages 中配置

1. 进入项目 **Settings** → **Custom domains**
2. 点击 **Set up a custom domain**
3. 输入域名（如 `app.yourdomain.com`）
4. Cloudflare 会自动添加 DNS 记录
5. 等待 SSL 证书配置完成

---

## 🔒 环境变量管理

### 前端变量（Cloudflare Pages）

所有前端变量必须以 `VITE_` 开头：

```bash
VITE_API_BASE_URL=https://your-backend.com
VITE_FIREBASE_API_KEY=xxx
VITE_FIREBASE_AUTH_DOMAIN=xxx
VITE_FIREBASE_DATABASE_URL=xxx
VITE_FIREBASE_PROJECT_ID=xxx
```

### 后端变量（外部服务）

在后端部署平台（Railway/Render）配置：

```bash
FIREBASE_API_KEY=xxx
FIREBASE_DATABASE_URL=xxx
NVIDIA_API=xxx
OPENAI_API=xxx
GEMINI_API=xxx
SMTP_USER=xxx
SMTP_PASS=xxx
SERPAPI_KEY=xxx
```

---

## 📊 部署后检查清单

- [ ] 前端成功构建并部署到 Cloudflare Pages
- [ ] 后端成功部署到外部服务
- [ ] 前端可以访问后端 API（CORS 配置正确）
- [ ] Firebase 集成正常工作
- [ ] 环境变量全部配置
- [ ] SPA 路由正常（_redirects 文件生效）
- [ ] 图像上传和分析功能正常
- [ ] 用户认证流程正常
- [ ] 自定义域名配置（如有）
- [ ] SSL 证书正常

---

## 🐛 常见问题

### 1. API 请求失败 (CORS 错误)

**原因**: 后端未配置正确的 CORS 源。

**解决**: 在 `backend/main.py` 的 `allow_origins` 中添加 Cloudflare Pages 域名。

### 2. 路由 404 错误

**原因**: 缺少 SPA 路由配置。

**解决**: 确保 `frontend/public/_redirects` 文件存在并包含 `/* /index.html 200`。

### 3. 环境变量未生效

**原因**: 
- 前端变量未以 `VITE_` 开头
- 部署后未重新构建

**解决**: 
- 重命名变量并重新部署
- 在 Cloudflare Pages 中触发重新部署

### 4. 构建失败

**原因**: 依赖安装失败或构建命令错误。

**解决**: 检查构建日志，确保：
- `package.json` 正确
- 构建命令路径正确（`cd frontend && npm run build`）
- Node.js 版本兼容（建议 18+）

### 5. 图像上传大小限制

**Cloudflare Pages**: 最大请求体 100MB（免费版）

**解决**: 
- 前端压缩图片后上传
- 或使用 Cloudflare Images 服务

---

## 💰 成本估算

### Cloudflare Pages (前端)
- **免费版**: 500 次构建/月，无限带宽
- **付费版**: $20/月起（更多构建次数）

### Cloudflare Workers (如使用)
- **免费版**: 100,000 请求/天
- **付费版**: $5/月起（1000 万请求）

### 外部后端
- **Railway**: $5/月起（500 小时执行时间）
- **Render**: 免费版有限制，付费 $7/月起
- **Google Cloud Run**: 按使用量计费，有免费额度

**推荐配置**: Cloudflare Pages (前端) + Railway (后端) ≈ $5-10/月

---

## 📚 相关文档

- [Cloudflare Pages 文档](https://developers.cloudflare.com/pages/)
- [Wrangler CLI 文档](https://developers.cloudflare.com/workers/wrangler/)
- [Cloudflare Workers 文档](https://developers.cloudflare.com/workers/)
- [Firebase Hosting](https://firebase.google.com/docs/hosting)（替代方案）

---

## 🎯 推荐部署方案

基于你的项目特点，**推荐方案 A**：

1. **前端**: Cloudflare Pages (快速、免费、CDN 加速)
2. **后端**: Railway 或 Render (支持 Python、快速部署)

这个方案：
- ✅ 部署简单，5 分钟内完成
- ✅ 成本低（$0-10/月）
- ✅ 无需重写后端代码
- ✅ 性能优秀（全球 CDN）
- ✅ 自动 HTTPS 和域名支持

---

**部署完成后，你的应用将运行在**:
- 前端: `https://relife-app.pages.dev`
- 后端: `https://relife-backend.railway.app`
- 自定义域名: `https://app.yourdomain.com` (可选)

需要帮助配置哪个步骤？
