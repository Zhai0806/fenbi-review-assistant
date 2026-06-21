# 📝 粉笔模考复盘助手

FastAPI + React 全栈。AI 错因诊断 + 矛盾分析 + 题型粒度统计 + 跨考趋势。支持行测/职测/公基三种考试类型。

## ✨ 功能

- **AI 错因诊断**：DeepSeek 批量诊断，输出具体错因 + 可执行对策
- **整体复盘分析**：下钻到模块→题型粒度，结合全站正确率+认知科学方法
- **矛盾分析**：按考试类型独立缓存，行测/职测和公基各自分析
- **知识洞察**：模块正确率、题型粒度、跨考趋势、用时-正确率矩阵
- **错题本**：跨考聚合、模块筛选、交互答题
- **AI 备考顾问**：多会话对话，结合个人知识库
- **申论批改**：AI 评分（内容/结构/语言）+ 素材库
- **笔记管理**：备考笔记 + 自定义链接

## 📋 项目结构

```
├── backend/                  # FastAPI 后端
│   ├── main.py               # 入口 + CORS + 路由注册
│   ├── db.py                 # 数据库依赖注入
│   ├── api/
│   │   ├── exams.py          # 模考抓取/列表/详情
│   │   ├── questions.py      # 题目更新/错题本/薄弱题型
│   │   ├── diagnose.py       # AI 诊断(SSE流式)/诊断列表/确认
│   │   ├── insights.py       # 知识洞察/矛盾分析/跨考对比/趋势
│   │   ├── chat.py           # AI 对话/会话管理
│   │   ├── shenlun.py        # 申论抓取/作答/批改/素材库
│   │   └── notes.py          # 笔记CRUD/链接管理
│   └── requirements.txt
├── frontend/                 # React + TypeScript 前端
│   └── src/pages/
│       ├── Dashboard.tsx     # 仪表盘
│       ├── ExamReview.tsx    # 模考复盘（题目浏览/诊断总览/答题卡）
│       ├── WrongBank.tsx     # 错题本
│       ├── Insights.tsx      # 知识洞察+矛盾分析
│       ├── AIChat.tsx        # AI 顾问
│       ├── Shenlun.tsx       # 申论练习
│       └── Notes.tsx         # 笔记+链接
├── utils/                    # Python 工具库
│   ├── db.py                 # SQLite 操作（KnowledgeDB）
│   ├── analysis.py           # 统计分析 + 矛盾分析 + 整体复盘
│   ├── llm.py                # LLM 调用封装
│   └── fetch.py              # 粉笔数据抓取
├── skills/
│   └── error_diagnosis.md    # 错因诊断 Skill（系统提示词）
├── data/
│   ├── reports/              # 抓取的模考报告
│   ├── user_profile.md       # 用户能力画像
│   └── user_config.json      # 用户策略配置
├── config.yaml               # 配置文件（Cookie / API Key）
├── start.bat                 # 一键启动
└── requirements.txt
```

## 🚀 快速开始

### 环境

Python 3.10+ / Node.js 18+

```bash
pip install -r requirements.txt
cd frontend && npm install
```

### 配置

复制 `config.example.yaml` 为 `config.yaml`，填入：

```yaml
fenbi:
  cookie: "你的粉笔Cookie"
  routecs: "xingce"

llm:
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com"
  api_key: "你的DeepSeek API Key"
```

### 启动

```bash
# 后端
uvicorn backend.main:app --port 8000 --reload

# 前端
cd frontend && npm run dev
```

打开 `http://localhost:5173`

## 📊 考试类型

| 类型 | 说明 |
|------|------|
| 行测/职测 | 公务员/事业单位职业能力测试 |
| 公基 | 公共基础知识（综合知识） |
| 申论 | 材料写作 + AI 批改 |
