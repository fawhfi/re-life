# 快速部署指南

## 🚀 5 分钟快速部署

### 前提条件
- Node.js 18+ 已安装
- 已有 Cloudflare 账号
- 已有后端部署服务账号（Railway/Render/Google Cloud）

---

## 第一步：部署前端到 Cloudflare Pages

### 方法 1：使用自动化脚本（推荐）

**Windows 用户**:
```bash
cd frontend
deploy-cloudflare.bat
```

**Mac/Linux 用户**:
```bash
cd frontend
chmod +x deploy-cloudflare.sh
./deploy-cloudflare.sh
```

按提示操作：
1. 首次运行会安装 Wrangler CLI
2. 输入项目名称（如 `relife-app`）
3. 等待构建和部署完成
4. 记录前端 URL：`https://relife-app.pages.dev`

### 方法 2：手动部署

```bash
cd frontend

# 1. 安装 Wrangler
npm install -g wrangler

# 2. 登录 Cloudflare
wrangler login

# 3. 创建环境变量文件
cp .env.production.template .env.production
# 编辑 .env.production 填入实际值

# 4. 构建
npm install
npm run build

# 5. 部署
wrangler pages deploy dist --project-name=relife-app
```

---

## 第二步：部署后端

### 选项 A：Railway（最简单）

```bash
cd backend

# 1. 安装 Railway CLI
npm install -g @railway/cli

# 2. 登录
railway login

# 3. 初始化项目
railway init

# 4. 添加环境变量
railway variables set FIREBASE_API_KEY="your_key"
railway variables set FIREBASE_DATABASE_URL="your_url"
railway variables set NVIDIA_API="your_key"
# ... 添加所有环境变量

# 5. 部署
railway up

# 6. 获取 URL
railway status
# 记录后端 URL，如：https://relife-backend.railway.app
```

### 选项 B：Render

1. 访问 https://render.com
2. 点击 **New +** → **Web Service**
3. 连接 GitHub 仓库
4. 配置：
   - **Name**: `relife-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Root Directory**: `backend`
5. 添加环境变量（点击 **Environment** 标签）
6. 点击 **Create Web Service**
7. 等待部署完成，记录 URL

### 选项 C：使用 Docker

```bash
cd backend

# 1. 构建镜像
docker build -t relife-backend .

# 2. 运行容器
docker run -p 8000:8000 \
  -e FIREBASE_API_KEY="your_key" \
  -e FIREBASE_DATABASE_URL="your_url" \
  relife-backend

# 3. 部署到云服务（Google Cloud Run 示例）
gcloud builds submit --tag gcr.io/YOUR_PROJECT/relife-backend
gcloud run deploy relife-backend \
  --image gcr.io/YOUR_PROJECT/relife-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## 第三步：连接前端和后端

### 1. 更新后端 CORS 配置

编辑 `backend/main.py`，找到 CORS 部分：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://relife-app.pages.dev",  # 👈 替换为你的前端 URL
        "http://localhost:5173",  # 开发环境
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

重新部署后端：
```bash
railway up  # 或在 Render 中触发重新部署
```

### 2. 更新前端环境变量

在 Cloudflare Pages Dashboard 中：

1. 进入你的项目
2. **Settings** → **Environment variables**
3. 添加变量：
   ```
   VITE_API_BASE_URL = https://relife-backend.railway.app
   ```
4. 点击 **Save**
5. 触发重新部署（**Deployments** → **Retry deployment**）

或使用命令行：
```bash
cd frontend
wrangler pages deployment create --project-name=relife-app
```

---

## 第四步：验证部署

### 1. 测试后端

```bash
# 健康检查
curl https://relife-backend.railway.app/api/health

# 应返回
{"status": "ok"}
```

### 2. 测试前端

访问 `https://relife-app.pages.dev`，检查：
- [ ] 页面正常加载
- [ ] 主题切换正常
- [ ] 语言切换正常

### 3. 测试完整流程

1. 注册/登录
2. 上传图片进行扫描
3. 查看分析结果
4. 检查记录页面
5. 测试奖励系统

---

## 常见问题快速修复

### ❌ API 请求失败

**检查**:
```bash
# 1. 查看浏览器控制台
F12 → Console → 查看错误信息

# 2. 检查后端状态
curl https://your-backend-url.com/api/health
```

**修复**:
- 确认后端 CORS 配置包含前端域名
- 确认前端 `VITE_API_BASE_URL` 正确

### ❌ 页面 404

**修复**:
- 确认 `frontend/public/_redirects` 文件存在
- 内容为：`/* /index.html 200`
- 重新部署前端

### ❌ 环境变量未生效

**修复**:
```bash
# 前端变量必须以 VITE_ 开头
VITE_API_BASE_URL=...  # ✅ 正确
API_BASE_URL=...       # ❌ 错误

# 修改后重新部署
cd frontend
npm run build
wrangler pages deploy dist --project-name=relife-app
```

### ❌ 图像上传失败

**检查**:
```bash
# 后端日志
railway logs  # Railway
# 或在 Render Dashboard 查看日志
```

**可能原因**:
- 图片太大（前端应压缩到 < 5MB）
- 后端内存不足（升级服务器配置）
- AI API 密钥未配置

---

## 自定义域名（可选）

### Cloudflare Pages 添加域名

1. 进入项目 **Settings** → **Custom domains**
2. 点击 **Set up a custom domain**
3. 输入域名（如 `app.yourdomain.com`）
4. Cloudflare 会自动添加 DNS 记录
5. 等待 SSL 证书生成（通常 < 5 分钟）

### Railway 添加域名

```bash
railway domain
```

按提示添加自定义域名。

---

## 性能优化建议

### 1. 启用 Cloudflare 缓存

在 `frontend/public/_headers` 中已配置：
```
/assets/*
  Cache-Control: public, max-age=31536000, immutable
```

### 2. 图片优化

使用 Cloudflare Images（可选）:
```bash
wrangler images upload image.jpg
```

### 3. 后端优化

在 `backend/main.py` 中启用 gzip：
```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

---

## 监控和日志

### 查看前端日志
```bash
# Cloudflare Pages 日志
wrangler pages deployment tail --project-name=relife-app
```

### 查看后端日志
```bash
# Railway
railway logs

# Render
# 在 Dashboard → Logs 查看

# Google Cloud Run
gcloud run services logs read relife-backend
```

---

## 成本估算

**每月成本**:
- Cloudflare Pages (前端): **$0** (免费版足够)
- Railway (后端): **$5** (Hobby 计划)
- Firebase: **$0** (免费版 - 10GB 存储，1GB 下载/天)

**总计**: **约 $5/月**

升级到付费版后：
- Cloudflare Pages Pro: $20/月（更多构建次数）
- Railway Pro: $20/月（更多资源）
- Firebase Blaze: 按使用量计费

---

## 下一步

- [ ] 配置自定义域名
- [ ] 设置 CI/CD 自动部署（GitHub Actions）
- [ ] 添加监控（Sentry、LogRocket）
- [ ] 性能优化（代码分割、懒加载）
- [ ] SEO 优化（meta 标签、sitemap）
- [ ] 添加 PWA 支持（Service Worker）

---

## 获取帮助

遇到问题？

1. 查看详细文档：`CLOUDFLARE_DEPLOYMENT.md`
2. 检查构建日志：Cloudflare Dashboard → Deployments
3. 检查后端状态：`curl https://your-backend-url.com/api/health`
4. 查看浏览器控制台错误信息

---

**🎉 恭喜！你的应用已经部署完成！**

访问 `https://relife-app.pages.dev` 查看效果。
