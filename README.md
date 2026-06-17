# Re-Life - 纯 React 重构版

可持续废物管理和回收智能平台，使用纯 React + FastAPI 架构。

## ✨ 特性

- ⚛️ 纯 React 18 单页应用
- 🎨 6 种主题切换
- 🌍 中英文支持
- 📱 响应式设计
- 🔥 Firebase 集成
- 🤖 多 AI 提供商
- 🧠 本地 CNN 模型

## 🚀 快速开始

### 1. 环境要求

- Node.js 18+
- Python 3.9+
- Firebase 项目

### 2. 安装

#### 后端
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 前端
```bash
cd frontend
npm install
```

### 3. 配置环境变量

复制 `.env.template` 为 `.env` 并填入实际值。

### 4. 启动服务

#### 后端
```bash
cd backend
python main.py
# 运行在 http://localhost:8000
```

#### 前端
```bash
cd frontend
npm run dev
# 运行在 http://localhost:5173
```

## 📁 项目结构

```
rel-react-refactored/
├── frontend/          # React 前端
│   ├── src/
│   │   ├── api/      # API 客户端
│   │   ├── components/  # 组件
│   │   ├── pages/    # 页面
│   │   ├── hooks/    # Hooks
│   │   ├── store/    # 状态管理
│   │   └── utils/    # 工具
│   └── package.json
│
└── backend/           # FastAPI 后端
    ├── api/          # 路由
    ├── models/       # ML 模型
    ├── services/     # 服务
    └── main.py
```

## 🔑 环境变量

### 必需配置

```bash
# Firebase
FIREBASE_API_KEY=your_key
FIREBASE_DATABASE_URL=your_url

# AI (至少配置一个)
NVIDIA_API=your_key
OPENAI_API=your_key
GEMINI_API=your_key
```

### 可选配置

```bash
# SMTP 邮件
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_password

# 新闻 API
SERPAPI_KEY=your_key
```

## 📊 核心功能

### 1. 图像扫描分析
- AI 智能识别
- CNN 备份分类
- 加权评分系统
- 处置指南

### 2. 记录管理
- Firebase 实时同步
- 统计数据
- 历史记录

### 3. 奖励系统
- 积分钱包
- 优惠券兑换
- 实时更新

### 4. 用户体验
- 主题切换
- 多语言
- 响应式设计

## 🤖 AI 集成

支持 5 个 AI 提供商：
- NVIDIA
- OpenAI
- Gemini
- DeepSeek
- Claude

AI 失败时自动使用本地 CNN 模型。

## ⚠️ 注意事项

1. 需要手动复制 CNN 模型文件：
   ```bash
   cp ../rel-react/models/model_INT8.onnx ./backend/models/
   ```

2. `backend/models/ai_providers.py` 是占位符，需要参考原项目补充

3. 开发模式下验证码会打印到终端

## 📚 文档

- `ARCHITECTURE.md` - 详细架构设计
- `SUMMARY.md` - 重构总结
- `.env.template` - 环境变量说明

## 📞 支持

查看原项目 `rel-react/` 获取完整参考实现。

---

**重构完成**: 2026-06-17  
**技术栈**: React 18 + FastAPI + Firebase + ONNX Runtime
