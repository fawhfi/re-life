# Re-Life 纯 React 架构设计

## 项目概述

将 Re-Life 从混合模式（Python 模板 + 部分 React）重构为纯 React SPA + FastAPI 后端。

## 技术栈

### 前端
- **React 19** - UI 框架
- **React Router v6** - 客户端路由
- **Firebase SDK** - 认证和实时数据库
- **Axios** - HTTP 客户端
- **React Query** - 服务器状态管理
- **Zustand** - 客户端状态管理
- **Vite** - 构建工具

### 后端
- **FastAPI** - Python Web 框架
- **ONNX Runtime** - 本地 CNN 模型推理
- **多 AI 提供商** - NVIDIA/OpenAI/Gemini/DeepSeek/Claude
- **Firebase Admin** - 后端 Firebase 集成（可选）

## 目录结构

```
rel-react-refactored/
├── frontend/                  # React 应用
│   ├── public/               # 静态资源
│   │   ├── assets/           # 图片、图标
│   │   └── index.html        # HTML 入口
│   ├── src/
│   │   ├── api/              # API 客户端
│   │   │   ├── client.js     # Axios 配置
│   │   │   ├── auth.js       # 认证 API
│   │   │   ├── scan.js       # 扫描 API
│   │   │   ├── records.js    # 记录 API
│   │   │   └── rewards.js    # 奖励 API
│   │   ├── components/       # React 组件
│   │   │   ├── common/       # 通用组件
│   │   │   │   ├── Button.jsx
│   │   │   │   ├── Modal.jsx
│   │   │   │   ├── Spinner.jsx
│   │   │   │   └── Toast.jsx
│   │   │   ├── layout/       # 布局组件
│   │   │   │   ├── Header.jsx
│   │   │   │   ├── Navigation.jsx
│   │   │   │   └── Layout.jsx
│   │   │   ├── scan/         # 扫描相关
│   │   │   │   ├── ScanUploader.jsx
│   │   │   │   ├── ScanResult.jsx
│   │   │   │   ├── WeightedScore.jsx
│   │   │   │   ├── DisposalGuide.jsx
│   │   │   │   └── Camera.jsx
│   │   │   ├── records/      # 记录相关
│   │   │   │   ├── RecordList.jsx
│   │   │   │   ├── RecordCard.jsx
│   │   │   │   └── RecordStats.jsx
│   │   │   ├── rewards/      # 奖励相关
│   │   │   │   ├── RewardsWallet.jsx
│   │   │   │   ├── RewardsCatalog.jsx
│   │   │   │   └── CouponCard.jsx
│   │   │   └── auth/         # 认证相关
│   │   │       ├── LoginForm.jsx
│   │   │       ├── RegisterForm.jsx
│   │   │       └── ForgotPassword.jsx
│   │   ├── pages/            # 页面组件
│   │   │   ├── HomePage.jsx
│   │   │   ├── RecordsPage.jsx
│   │   │   ├── RewardsPage.jsx
│   │   │   ├── SettingsPage.jsx
│   │   │   ├── LoginPage.jsx
│   │   │   └── RegisterPage.jsx
│   │   ├── hooks/            # 自定义 Hooks
│   │   │   ├── useAuth.js
│   │   │   ├── useFirebase.js
│   │   │   ├── useScan.js
│   │   │   ├── useRecords.js
│   │   │   ├── useRewards.js
│   │   │   └── useCamera.js
│   │   ├── store/            # Zustand 状态管理
│   │   │   ├── authStore.js
│   │   │   ├── scanStore.js
│   │   │   ├── uiStore.js
│   │   │   └── settingsStore.js
│   │   ├── utils/            # 工具函数
│   │   │   ├── firebase.js
│   │   │   ├── storage.js
│   │   │   ├── validation.js
│   │   │   ├── scoring.js
│   │   │   └── i18n.js
│   │   ├── styles/           # 样式
│   │   │   ├── globals.css
│   │   │   ├── themes.css
│   │   │   └── animations.css
│   │   ├── constants/        # 常量配置
│   │   │   ├── schemas.js
│   │   │   ├── disposalGuides.js
│   │   │   └── rewards.js
│   │   ├── App.jsx           # 根组件
│   │   ├── main.jsx          # 入口文件
│   │   └── router.jsx        # 路由配置
│   ├── package.json
│   ├── vite.config.js
│   └── .env.local            # 前端环境变量
│
├── backend/                   # FastAPI 后端
│   ├── api/
│   │   ├── __init__.py
│   │   ├── scan.py           # 扫描端点
│   │   ├── auth.py           # 认证端点
│   │   ├── data.py           # 数据端点
│   │   └── health.py         # 健康检查
│   ├── core/
│   │   ├── config.py         # 配置管理
│   │   ├── security.py       # 安全工具
│   │   └── middleware.py     # 中间件
│   ├── models/
│   │   ├── cnn.py            # CNN 分类器
│   │   ├── ai_providers.py   # AI 提供商
│   │   └── schemas.py        # Pydantic 模型
│   ├── services/
│   │   ├── email.py          # 邮件服务
│   │   ├── firebase.py       # Firebase 服务
│   │   └── news.py           # 新闻服务
│   ├── models/               # ONNX 模型文件
│   │   └── model_INT8.onnx
│   ├── main.py               # FastAPI 应用入口
│   ├── requirements.txt
│   └── .env                  # 后端环境变量
│
├── .env.template             # 环境变量模板
├── README.md                 # 项目说明
└── docker-compose.yml        # Docker 配置（可选）
```

## 核心功能模块

### 1. 认证系统
- Firebase Authentication (前端)
- 邮箱验证码登录/注册
- 密码重置
- 会话管理
- 速率限制

### 2. 图像扫描分析
- 图像上传（拖拽/选择/相机）
- 多 AI 提供商支持
- 本地 CNN 备份
- 实时分析反馈
- 加权评分系统

### 3. 记录管理
- Firebase Realtime Database 存储
- 实时同步
- 统计计算
- 筛选和排序

### 4. 奖励系统
- 积分钱包
- 优惠券兑换
- 历史记录

### 5. 多语言支持
- 中文/英文切换
- 动态加载语言包

### 6. 主题系统
- 6 种主题切换
- CSS 变量实现
- 持久化设置

## 数据流

### 扫描流程
```
用户上传图片
    ↓
前端压缩预处理
    ↓
发送到 /api/scan/ai
    ↓
后端 AI 分析 → 失败则使用 CNN
    ↓
返回评分和建议
    ↓
前端展示结果
    ↓
用户确认添加到记录
    ↓
保存到 Firebase
```

### 认证流程
```
用户输入邮箱
    ↓
前端调用 /api/send-verification
    ↓
后端发送验证码（或控制台显示）
    ↓
用户输入验证码
    ↓
前端调用 /api/verify-code
    ↓
后端验证并返回 token
    ↓
前端使用 Firebase SDK 认证
    ↓
获取用户数据
```

## API 端点

### 认证
- `POST /api/send-verification` - 发送验证码
- `POST /api/verify-code` - 验证码确认
- `POST /api/forgot-password` - 忘记密码
- `POST /api/reset-password` - 重置密码

### 扫描
- `POST /api/scan/ai` - AI 图像分析
  - 支持 `mode`: dispose/purchase
  - 支持 `item_type`: food/general
  - 支持 `item_state`: new/expire

### 数据
- `GET /api/news` - 获取环保新闻
- `GET /api/schemas` - 获取评分模式
- `GET /api/rewards` - 获取奖励目录
- `POST /api/rewards/redeem` - 兑换奖励
- `GET /api/fact` - 获取环保知识

## 状态管理策略

### Zustand Stores

1. **authStore** - 认证状态
   ```js
   {
     user: null | User,
     isAuthenticated: boolean,
     loading: boolean,
     login: (email, code) => Promise,
     logout: () => void,
     updateProfile: (data) => void
   }
   ```

2. **scanStore** - 扫描状态
   ```js
   {
     mode: 'dispose' | 'purchase',
     result: null | ScanResult,
     loading: boolean,
     setMode: (mode) => void,
     scan: (file, options) => Promise,
     reset: () => void
   }
   ```

3. **uiStore** - UI 状态
   ```js
   {
     theme: string,
     language: 'en' | 'zh',
     soundEnabled: boolean,
     showModal: boolean,
     modalContent: any,
     setTheme: (theme) => void,
     setLanguage: (lang) => void
   }
   ```

## 关键特性保留

### ✅ 本地 CNN 模型
- 服务器端运行 ONNX Runtime
- AI API 失败时自动回退
- 6 类垃圾分类（glass/metal/organic/paper/plastic/ewaste）

### ✅ 多 AI 提供商
- NVIDIA
- OpenAI
- Google Gemini
- DeepSeek
- Anthropic Claude
- 配置灵活，支持动态切换

### ✅ Firebase 集成
- Realtime Database 用于数据存储
- Authentication 用于用户管理
- 客户端 SDK 直接通信

### ✅ 加权评分系统
- 4 种评分模式（food_new/food_expire/item_new/item_expire）
- 5 个维度加权计算
- 动态等级判定

### ✅ 响应式设计
- 移动端优先
- 触摸友好
- PWA 支持（可选）

## 安全考虑

1. **CORS 配置** - 限制允许的源
2. **速率限制** - 防止 API 滥用
3. **输入验证** - 后端 Pydantic 验证
4. **图像大小限制** - 10MB 最大上传
5. **安全头** - CSP、HSTS 等
6. **Firebase 规则** - 数据访问控制

## 部署方案

### 开发环境
```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev  # 运行在 http://localhost:5173
```

### 生产环境
- 前端：Vercel / Netlify / Firebase Hosting
- 后端：Railway / Render / Google Cloud Run
- 或使用 Docker Compose 一键部署

## 下一步

1. ✅ 创建 .env.template
2. 🔄 设计架构文档
3. ⏳ 创建前端项目结构
4. ⏳ 实现核心组件
5. ⏳ 配置路由和状态管理
6. ⏳ 集成 Firebase
7. ⏳ 连接后端 API
8. ⏳ 测试和优化
