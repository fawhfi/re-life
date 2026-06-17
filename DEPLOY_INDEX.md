# Re-Life - Cloudflare 部署完整指南

## 📚 文档索引

本项目包含完整的 Cloudflare 部署文档和工具。以下是所有相关文件：

### 📖 部署文档

1. **[DEPLOYMENT_SUMMARY.md](./DEPLOYMENT_SUMMARY.md)** ⭐ **从这里开始**
   - 部署概述和推荐方案
   - 快速步骤说明
   - 所有文件清单

2. **[QUICK_DEPLOY.md](./QUICK_DEPLOY.md)** - 5 分钟快速部署
   - 最简化的部署流程
   - 命令行示例
   - 常见问题快速修复

3. **[CLOUDFLARE_DEPLOYMENT.md](./CLOUDFLARE_DEPLOYMENT.md)** - 详细完整指南
   - 3 种部署架构方案
   - 详细配置说明
   - 成本分析
   - 故障排除

4. **[DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)** - 部署检查清单
   - 逐项检查列表
   - 测试验证步骤
   - 环境变量清单

### 🛠️ 部署工具

#### 前端工具
- `frontend/deploy-cloudflare.bat` - Windows 自动部署脚本
- `frontend/deploy-cloudflare.sh` - Linux/Mac 自动部署脚本
- `frontend/public/_redirects` - SPA 路由配置
- `frontend/public/_headers` - 安全头和缓存配置
- `frontend/.env.production.template` - 环境变量模板

#### 后端工具
- `backend/Dockerfile` - Docker 容器配置
- `backend/railway.json` - Railway 部署配置
- `backend/cors_config_example.py` - CORS 配置示例

#### 测试工具
- `test-local.bat` - Windows 本地测试脚本
- `test-local.sh` - Linux/Mac 本地测试脚本

#### CI/CD
- `.github/workflows/deploy.yml` - GitHub Actions 自动部署
- `wrangler.toml` - Wrangler CLI 配置

### 📋 其他文档
- **[README.md](./README.md)** - 项目总览
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - 技术架构
- **[SUMMARY.md](./SUMMARY.md)** - 重构总结

---

## 🚀 快速开始

### 新用户？从这里开始：

1. **阅读概述** → [DEPLOYMENT_SUMMARY.md](./DEPLOYMENT_SUMMARY.md)
2. **快速部署** → [QUICK_DEPLOY.md](./QUICK_DEPLOY.md)
3. **完整验证** → [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)

### 推荐部署流程：

```bash
# 1. 本地测试（可选但推荐）
# Windows:
test-local.bat

# Linux/Mac:
chmod +x test-local.sh
./test-local.sh

# 2. 部署后端到 Railway
cd backend
npm install -g @railway/cli
railway login
railway init
railway up

# 3. 部署前端到 Cloudflare Pages
cd ../frontend

# Windows:
deploy-cloudflare.bat

# Linux/Mac:
chmod +x deploy-cloudflare.sh
./deploy-cloudflare.sh

# 4. 配置环境变量（参考 DEPLOYMENT_CHECKLIST.md）

# 5. 验证部署
curl https://your-backend.railway.app/api/health
curl https://your-app.pages.dev
```

---

## 🎯 推荐部署方案

**前端**: Cloudflare Pages  
**后端**: Railway (或 Render/Google Cloud Run)  
**数据库**: Firebase Realtime Database  
**成本**: 约 $5/月

### 为什么选择这个方案？

✅ **简单** - 10 分钟内完成部署  
✅ **便宜** - 前端免费，后端 $5/月  
✅ **快速** - 全球 CDN 加速  
✅ **可靠** - 自动 HTTPS 和备份  
✅ **灵活** - 支持 Python 和机器学习模型  

---

## 📦 需要配置的环境变量

### 前端 (Cloudflare Pages)

```bash
VITE_API_BASE_URL=https://your-backend.railway.app
VITE_FIREBASE_API_KEY=your_firebase_key
VITE_FIREBASE_AUTH_DOMAIN=your-app.firebaseapp.com
VITE_FIREBASE_DATABASE_URL=https://your-app.firebaseio.com
VITE_FIREBASE_PROJECT_ID=your_project_id
VITE_FIREBASE_STORAGE_BUCKET=your-app.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
VITE_FIREBASE_APP_ID=your_app_id
```

### 后端 (Railway/Render)

```bash
FIREBASE_API_KEY=your_key
FIREBASE_DATABASE_URL=your_url
NVIDIA_API=your_nvidia_key  # 或 OPENAI_API 或 GEMINI_API
CORS_ORIGINS=https://your-app.pages.dev
ENVIRONMENT=production
```

详细配置见 [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md)

---

## 🐛 遇到问题？

### 常见问题快速跳转：

- **CORS 错误** → [QUICK_DEPLOY.md#常见问题快速修复](./QUICK_DEPLOY.md)
- **环境变量未生效** → [DEPLOYMENT_CHECKLIST.md#环境变量](./DEPLOYMENT_CHECKLIST.md)
- **构建失败** → [CLOUDFLARE_DEPLOYMENT.md#常见问题](./CLOUDFLARE_DEPLOYMENT.md)
- **API 请求失败** → [QUICK_DEPLOY.md#API请求失败](./QUICK_DEPLOY.md)

### 调试步骤：

1. 检查浏览器控制台 (F12)
2. 验证后端健康: `curl https://your-backend.com/api/health`
3. 检查 Cloudflare Pages 构建日志
4. 验证环境变量配置
5. 查看后端日志: `railway logs`

---

## 📞 获取帮助

- 📖 查看详细文档（见上方索引）
- 🔍 运行本地测试脚本
- 🌐 访问 [Cloudflare Pages 文档](https://developers.cloudflare.com/pages/)
- 🚂 访问 [Railway 文档](https://docs.railway.app/)

---

## ✅ 部署成功标志

当你看到以下结果时，部署成功：

- ✅ `curl https://your-backend.com/api/health` 返回 `{"status":"healthy"}`
- ✅ `https://your-app.pages.dev` 可以访问
- ✅ 前端可以成功调用后端 API（无 CORS 错误）
- ✅ 可以注册、登录
- ✅ 图片扫描功能正常工作
- ✅ 数据保存到 Firebase

---

## 🎉 下一步

部署完成后，你可以：

1. **配置自定义域名** - 在 Cloudflare Pages 添加域名
2. **设置 CI/CD** - 使用 GitHub Actions 自动部署
3. **添加监控** - 集成 Sentry 进行错误追踪
4. **性能优化** - 启用缓存、代码分割
5. **SEO 优化** - 添加 meta 标签、sitemap

---

**准备好了吗？立即开始部署！** 🚀

阅读 [DEPLOYMENT_SUMMARY.md](./DEPLOYMENT_SUMMARY.md) 开始你的部署之旅。
