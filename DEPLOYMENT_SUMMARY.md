# 部署总结 - Cloudflare Pages

## 📦 已创建的文件

为了帮助你部署到 Cloudflare，我已经创建了以下文件：

### 📄 文档
1. **CLOUDFLARE_DEPLOYMENT.md** - 完整的 Cloudflare 部署指南
   - 3 种部署架构方案
   - 详细的步骤说明
   - 常见问题解决方案
   - 成本估算

2. **QUICK_DEPLOY.md** - 5 分钟快速部署指南
   - 快速上手步骤
   - 命令行示例
   - 故障排除技巧

3. **DEPLOYMENT_CHECKLIST.md** - 部署检查清单
   - 完整的检查项
   - 测试验证步骤
   - 部署后验证命令

### ⚙️ 配置文件

#### 前端
1. **frontend/.env.production.template** - 生产环境变量模板
2. **frontend/public/_redirects** - SPA 路由配置
3. **frontend/public/_headers** - 安全头和缓存配置
4. **frontend/vite.config.js** - 优化的构建配置（已更新）
5. **frontend/deploy-cloudflare.bat** - Windows 部署脚本
6. **frontend/deploy-cloudflare.sh** - Linux/Mac 部署脚本

#### 后端
1. **backend/Dockerfile** - Docker 容器配置
2. **backend/railway.json** - Railway 部署配置
3. **backend/core/config.py** - CORS 配置（已更新）
4. **backend/cors_config_example.py** - CORS 配置示例

#### CI/CD
1. **.github/workflows/deploy.yml** - GitHub Actions 自动部署
2. **wrangler.toml** - Wrangler CLI 配置
3. **.gitignore** - Git 忽略文件配置

---

## 🚀 推荐部署方案

基于你的项目架构（React + FastAPI + Firebase + ONNX），我推荐：

### 方案：Cloudflare Pages (前端) + Railway (后端)

**优势**：
- ✅ 部署简单快速（< 10 分钟）
- ✅ 成本低（约 $5/月）
- ✅ 无需修改代码
- ✅ 全球 CDN 加速
- ✅ 自动 HTTPS
- ✅ 支持 Python 和机器学习模型

---

## 📋 部署步骤概览

### 第一步：部署后端到 Railway

```bash
cd backend

# 1. 安装 Railway CLI
npm install -g @railway/cli

# 2. 登录并初始化
railway login
railway init

# 3. 添加环境变量（在 Railway Dashboard 或命令行）
railway variables set FIREBASE_API_KEY="your_key"
railway variables set NVIDIA_API="your_key"
# ... 其他环境变量

# 4. 部署
railway up

# 5. 获取后端 URL
railway domain
# 例如: https://relife-backend.railway.app
```

### 第二步：部署前端到 Cloudflare Pages

```bash
cd frontend

# 1. 复制环境变量模板
cp .env.production.template .env.production

# 2. 编辑 .env.production，填入后端 URL
# VITE_API_BASE_URL=https://relife-backend.railway.app

# 3. 运行部署脚本
# Windows:
deploy-cloudflare.bat

# Linux/Mac:
chmod +x deploy-cloudflare.sh
./deploy-cloudflare.sh

# 4. 获取前端 URL
# 例如: https://relife-app.pages.dev
```

### 第三步：更新后端 CORS

在 Railway Dashboard 添加环境变量：
```
CORS_ORIGINS=https://relife-app.pages.dev,https://your-custom-domain.com
```

重新部署后端。

### 第四步：在 Cloudflare Pages 配置环境变量

1. 登录 Cloudflare Dashboard
2. 进入 Pages → 你的项目
3. Settings → Environment variables
4. 添加所有 `VITE_*` 变量
5. 触发重新部署

---

## 🔍 需要配置的环境变量

### 前端环境变量 (Cloudflare Pages)

必需：
```bash
VITE_API_BASE_URL=https://your-backend-url.com
VITE_FIREBASE_API_KEY=your_firebase_api_key
VITE_FIREBASE_AUTH_DOMAIN=your-app.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://your-app.firebaseio.com
VITE_FIREBASE_PROJECT_ID=your_project_id
VITE_FIREBASE_STORAGE_BUCKET=your-app.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

### 后端环境变量 (Railway/Render)

必需：
```bash
FIREBASE_API_KEY=your_key
FIREBASE_DATABASE_URL=your_url
NVIDIA_API=your_nvidia_key
# 或
OPENAI_API=your_openai_key
# 或
GEMINI_API=your_gemini_key
```

可选：
```bash
DEEPSEEK_API=your_key
CLAUDE_API=your_key
SMTP_USER=your_email
SMTP_PASS=your_password
SERPAPI_KEY=your_key
CORS_ORIGINS=https://your-frontend.pages.dev
ENVIRONMENT=production
```

---

## ✅ 部署后验证

运行这些命令验证部署：

```bash
# 1. 检查后端健康
curl https://your-backend.railway.app/api/health
# 应返回: {"status":"healthy","version":"2.0.0"}

# 2. 检查前端
curl -I https://relife-app.pages.dev
# 应返回: 200 OK

# 3. 检查 CORS
curl -H "Origin: https://relife-app.pages.dev" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     https://your-backend.railway.app/api/scan/ai
# 应包含 Access-Control-Allow-Origin 头
```

在浏览器中：
1. 访问 `https://relife-app.pages.dev`
2. 打开浏览器控制台 (F12)
3. 检查是否有错误
4. 测试注册/登录
5. 测试图片扫描功能

---

## 🐛 常见问题

### 问题 1: CORS 错误
```
Access to fetch at 'https://backend.com/api' from origin 'https://frontend.pages.dev' 
has been blocked by CORS policy
```

**解决**：
1. 在 Railway 添加环境变量：`CORS_ORIGINS=https://relife-app.pages.dev`
2. 重新部署后端
3. 清除浏览器缓存

### 问题 2: 环境变量未生效

**解决**：
1. 确认前端变量以 `VITE_` 开头
2. 在 Cloudflare Pages Dashboard 配置变量
3. 触发重新部署（不是重新发布）

### 问题 3: 构建失败

**解决**：
1. 检查 `package.json` 是否正确
2. 确认 Node.js 版本 18+
3. 查看构建日志找到具体错误
4. 本地测试构建：`npm run build`

---

## 💰 预估成本

- **Cloudflare Pages**: $0/月（免费版）
- **Railway**: $5/月（Hobby 计划，500 小时）
- **Firebase**: $0/月（免费版，10GB 存储）

**总计**: 约 **$5/月**

---

## 📚 相关文档链接

- [Cloudflare Pages 官方文档](https://developers.cloudflare.com/pages/)
- [Railway 文档](https://docs.railway.app/)
- [Wrangler CLI 文档](https://developers.cloudflare.com/workers/wrangler/)
- [Vite 生产构建](https://vitejs.dev/guide/build.html)

---

## 🎯 下一步

1. **立即部署**：按照 `QUICK_DEPLOY.md` 开始
2. **CI/CD**：配置 GitHub Actions 实现自动部署
3. **自定义域名**：在 Cloudflare Pages 添加域名
4. **监控**：集成 Sentry 或其他监控工具
5. **性能优化**：启用缓存、代码分割

---

## 📞 需要帮助？

- 查看 `CLOUDFLARE_DEPLOYMENT.md` 获取详细步骤
- 查看 `DEPLOYMENT_CHECKLIST.md` 进行完整检查
- 检查浏览器控制台和后端日志
- 验证所有环境变量已正确配置

---

**准备好了吗？开始部署！** 🚀

Windows 用户：
```bash
cd frontend
deploy-cloudflare.bat
```

Mac/Linux 用户：
```bash
cd frontend
chmod +x deploy-cloudflare.sh
./deploy-cloudflare.sh
```
