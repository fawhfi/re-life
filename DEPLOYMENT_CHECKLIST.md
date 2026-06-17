"""
Cloudflare 部署检查清单

在部署之前，请确保完成以下所有步骤：
"""

## ✅ 前端准备

### 必需文件
- [ ] `frontend/public/_redirects` - SPA 路由重定向
- [ ] `frontend/public/_headers` - 安全头配置
- [ ] `frontend/.env.production` - 生产环境变量
- [ ] `frontend/vite.config.js` - 优化的构建配置

### 环境变量 (Cloudflare Pages)
- [ ] `VITE_API_BASE_URL` - 后端 API 地址
- [ ] `VITE_FIREBASE_API_KEY` - Firebase API 密钥
- [ ] `VITE_FIREBASE_AUTH_DOMAIN` - Firebase 认证域名
- [ ] `VITE_FIREBASE_DATABASE_URL` - Firebase 数据库 URL
- [ ] `VITE_FIREBASE_PROJECT_ID` - Firebase 项目 ID
- [ ] `VITE_FIREBASE_STORAGE_BUCKET` - Firebase 存储桶
- [ ] `VITE_FIREBASE_MESSAGING_SENDER_ID` - Firebase 消息发送者 ID
- [ ] `VITE_FIREBASE_APP_ID` - Firebase 应用 ID

### 构建测试
```bash
cd frontend
npm install
npm run build
# 检查 dist/ 目录是否生成
```

---

## ✅ 后端准备

### 必需文件
- [ ] `backend/requirements.txt` - Python 依赖
- [ ] `backend/Dockerfile` - Docker 镜像配置
- [ ] `backend/railway.json` - Railway 部署配置
- [ ] `backend/models/model_INT8.onnx` - CNN 模型文件

### 环境变量 (Railway/Render/Cloud Run)
- [ ] `FIREBASE_API_KEY` - Firebase API 密钥
- [ ] `FIREBASE_DATABASE_URL` - Firebase 数据库 URL
- [ ] `NVIDIA_API` - NVIDIA API 密钥
- [ ] `OPENAI_API` - OpenAI API 密钥
- [ ] `GEMINI_API` - Google Gemini API 密钥
- [ ] `DEEPSEEK_API` - DeepSeek API 密钥 (可选)
- [ ] `CLAUDE_API` - Anthropic Claude API 密钥 (可选)
- [ ] `SMTP_USER` - SMTP 邮箱用户名 (可选)
- [ ] `SMTP_PASS` - SMTP 邮箱密码 (可选)
- [ ] `SERPAPI_KEY` - SerpAPI 密钥 (可选)

### CORS 配置
- [ ] 在 `backend/main.py` 中添加前端域名到 `allow_origins`

### 本地测试
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
# 访问 http://localhost:8000/api/health
```

---

## ✅ 部署步骤

### 1. 部署后端
- [ ] 选择后端平台 (Railway/Render/Google Cloud Run)
- [ ] 配置所有环境变量
- [ ] 部署并获取后端 URL
- [ ] 测试健康检查: `curl https://your-backend.com/api/health`

### 2. 更新后端 CORS
- [ ] 在 `backend/main.py` 中添加 Cloudflare Pages 域名
- [ ] 重新部署后端

### 3. 部署前端
- [ ] 安装 Wrangler CLI: `npm install -g wrangler`
- [ ] 登录 Cloudflare: `wrangler login`
- [ ] 在 Cloudflare Pages 配置环境变量
- [ ] 运行部署脚本或手动部署
- [ ] 获取前端 URL: `https://your-app.pages.dev`

### 4. 连接测试
- [ ] 前端可以访问
- [ ] 后端 API 可以访问
- [ ] 前端可以成功调用后端 API (无 CORS 错误)
- [ ] Firebase 集成正常

---

## ✅ 功能测试

### 认证功能
- [ ] 注册新用户
- [ ] 登录
- [ ] 邮箱验证码接收
- [ ] 密码重置

### 扫描功能
- [ ] 图片上传
- [ ] AI 分析返回结果
- [ ] 评分显示正确
- [ ] 处置建议显示

### 记录管理
- [ ] 添加记录到 Firebase
- [ ] 查看历史记录
- [ ] 统计数据正确
- [ ] 实时同步

### 奖励系统
- [ ] 查看钱包余额
- [ ] 兑换优惠券
- [ ] 历史记录显示

### UI/UX
- [ ] 主题切换正常
- [ ] 语言切换正常 (中/英)
- [ ] 移动端响应式布局
- [ ] 加载动画显示

---

## ✅ 性能优化

- [ ] 前端代码分割 (vendor chunks)
- [ ] 图片懒加载
- [ ] 启用 gzip 压缩 (后端)
- [ ] Cloudflare CDN 缓存配置
- [ ] 安全头配置 (_headers 文件)

---

## ✅ 安全检查

- [ ] CORS 配置限制域名 (不使用 `*`)
- [ ] 环境变量不包含在代码中
- [ ] Firebase 规则配置正确
- [ ] API 速率限制启用
- [ ] HTTPS 强制启用
- [ ] 安全响应头配置

---

## ✅ 监控和日志

- [ ] 设置错误监控 (Sentry 等)
- [ ] 配置日志收集
- [ ] 设置性能监控
- [ ] 配置正常运行时间监控

---

## ✅ 文档和备份

- [ ] 记录前端 URL
- [ ] 记录后端 URL
- [ ] 记录所有环境变量 (安全保存)
- [ ] 备份 Firebase 配置
- [ ] 文档化部署流程

---

## 🚨 常见问题预检查

### API 请求失败
✅ 检查项:
- 后端 CORS 包含前端域名
- `VITE_API_BASE_URL` 配置正确
- 后端服务正在运行
- 网络请求未被阻止

### 页面 404
✅ 检查项:
- `_redirects` 文件存在
- 内容为 `/* /index.html 200`
- 已重新部署

### 环境变量无效
✅ 检查项:
- 前端变量以 `VITE_` 开头
- 在 Cloudflare Pages Dashboard 配置
- 配置后重新部署

### Firebase 连接失败
✅ 检查项:
- 所有 Firebase 配置变量正确
- Firebase 项目启用了 Authentication 和 Realtime Database
- Firebase 规则允许访问

---

## 📊 部署后验证命令

```bash
# 1. 检查前端
curl -I https://your-app.pages.dev
# 应返回 200 状态码

# 2. 检查后端健康
curl https://your-backend.com/api/health
# 应返回 {"status": "healthy"}

# 3. 检查 CORS
curl -H "Origin: https://your-app.pages.dev" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     https://your-backend.com/api/scan/ai
# 应包含 Access-Control-Allow-Origin 头

# 4. 检查 DNS
nslookup your-app.pages.dev
# 应解析到 Cloudflare IP

# 5. 检查 SSL
openssl s_client -connect your-app.pages.dev:443 -servername your-app.pages.dev
# 应显示有效证书
```

---

## 🎯 部署成功标志

所有以下条件都满足时，部署成功：

✅ 前端可以通过 HTTPS 访问
✅ 后端健康检查返回 OK
✅ 前端可以成功调用后端 API
✅ 用户可以注册和登录
✅ 图片扫描功能正常工作
✅ 数据可以保存到 Firebase
✅ 无控制台错误
✅ 移动端正常显示

---

## 📞 获取帮助

如果遇到问题：

1. 查看 `QUICK_DEPLOY.md` - 快速部署指南
2. 查看 `CLOUDFLARE_DEPLOYMENT.md` - 详细部署文档
3. 检查浏览器控制台 (F12)
4. 查看后端日志
5. 检查 Cloudflare Pages 构建日志

---

**准备好了吗？开始部署！** 🚀

使用脚本快速部署：
- Windows: `cd frontend && deploy-cloudflare.bat`
- Mac/Linux: `cd frontend && chmod +x deploy-cloudflare.sh && ./deploy-cloudflare.sh`
