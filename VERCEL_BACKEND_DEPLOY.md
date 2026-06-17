# Vercel 后端部署指南

## 🎯 架构

**前端**: Cloudflare Pages  
**后端**: Vercel (Python Serverless Functions)

---

## 🚀 Vercel 部署后端

### 步骤1: 导入项目到 Vercel

1. 访问 https://vercel.com/new
2. 选择 **Import Git Repository**
3. 选择仓库：`fawhfi/re-life`
4. 选择分支：`react-prod`
5. 点击 **Deploy**

---

## 🔑 环境变量配置

在 Vercel Dashboard → Settings → Environment Variables 添加：

### 已有的变量（保持不变）
```
FIREBASE_AUTH_DOMAIN
FIREBASE_PROJECT_ID
FIREBASE_STORAGE_BUCKET
FIREBASE_MESSAGING_SENDER_ID
FIREBASE_APP_ID
FIREBASE_DATABASE_URL
NVIDIA_API
SMTP_USER
SMTP_PASS
SERPAPI_KEY
```

### 需要新增的变量
```
FIREBASE_API_KEY = your_firebase_api_key
CORS_ORIGINS = https://your-cloudflare-pages.pages.dev
ENVIRONMENT = production
```

---

## 🔗 获取后端 URL

部署完成后，你会得到类似这样的 URL：
```
https://your-project.vercel.app
```

---

## 🌐 配置 Cloudflare Pages

在 Cloudflare Pages 环境变量中添加：

```
VITE_API_BASE_URL = https://your-project.vercel.app
```

然后重新部署 Cloudflare Pages。

---

## ✅ 验证部署

```bash
# 检查后端
curl https://your-project.vercel.app/api/health

# 应返回: {"status":"healthy","version":"2.0.0"}
```

---

## 📊 最终架构

```
Cloudflare Pages (前端) → Vercel (后端) → Firebase (数据库)
```

**成本**: $0/月（Hobby 计划）或 $20/月（Pro 计划）

---

**准备好了吗？现在就部署！** 🚀
