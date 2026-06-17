# Vercel 部署指南

## 🚀 快速部署到 Vercel

### 方式1: 通过 GitHub 自动部署（推荐）

1. 访问 https://vercel.com
2. 点击 **Import Project**
3. 选择 **Import Git Repository**
4. 连接你的 GitHub 账号
5. 选择仓库：`fawhfi/re-life`
6. 选择分支：`react-prod`
7. 配置构建设置（见下方）
8. 点击 **Deploy**

---

## ⚙️ Vercel 构建配置

### Framework Preset
选择：**Other**

### Build & Development Settings

**Build Command**:
```bash
cd frontend && npm install && npm run build
```

**Output Directory**:
```bash
frontend/dist
```

**Install Command**:
```bash
npm install
```

**Root Directory**: 留空或 `/`

---

## 🔑 环境变量配置

### 必需的前端环境变量（VITE_开头）

在 Vercel Dashboard → Settings → Environment Variables 添加：

```
VITE_API_BASE_URL = https://your-project.vercel.app/api
VITE_FIREBASE_API_KEY = (你的 Firebase API Key)
VITE_FIREBASE_AUTH_DOMAIN = your-app.firebaseapp.com
VITE_FIREBASE_DATABASE_URL = https://your-app.firebaseio.com
VITE_FIREBASE_PROJECT_ID = your-project-id
VITE_FIREBASE_STORAGE_BUCKET = your-app.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID = 123456789
VITE_FIREBASE_APP_ID = 1:123456789:web:abc123
```

### 已有的后端环境变量

这些你已经配置好了，无需修改：
- ✅ FIREBASE_AUTH_DOMAIN
- ✅ FIREBASE_PROJECT_ID
- ✅ FIREBASE_STORAGE_BUCKET
- ✅ FIREBASE_MESSAGING_SENDER_ID
- ✅ FIREBASE_APP_ID
- ✅ FIREBASE_DATABASE_URL
- ✅ SERPAPI_KEY
- ✅ SMTP_USER
- ✅ SMTP_PASS
- ✅ NVIDIA_API

### 额外需要添加的后端环境变量

```
FIREBASE_API_KEY = (你的 Firebase API Key)
CORS_ORIGINS = https://your-project.vercel.app
ENVIRONMENT = production
```

---

## 🚀 部署步骤

### 1. 推送配置到 GitHub

```bash
git add vercel.json VERCEL_DEPLOY.md
git commit -m "Add Vercel deployment configuration"
git push origin react-prod
```

### 2. 在 Vercel 导入项目

1. 访问 https://vercel.com
2. Import Git Repository
3. 选择 `fawhfi/re-life` → `react-prod` 分支

### 3. 配置环境变量

添加所有 `VITE_*` 前端变量

### 4. 部署

点击 **Deploy**，等待构建完成

### 5. 验证

```bash
# 检查前端
curl https://your-project.vercel.app

# 检查后端 API
curl https://your-project.vercel.app/api/health
```

---

## 💡 重要提示

- API 地址：`https://your-project.vercel.app/api`
- 每次推送到 `react-prod` 自动部署
- 前端和后端都在同一个 Vercel 项目中

---

**准备好了吗？现在就推送配置并在 Vercel 部署！** 🚀
