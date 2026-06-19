# 📝 粉笔模考复盘助手

基于 FastAPI + React 的行测/职测/申论模考数据分析工具。抓取粉笔模考数据，AI 诊断错题，构建长期备考知识库。

## ✨ 功能特性

- **一键抓取**：支持行测/职测/三支一扶/申论等考试类型
- **AI 智能诊断**：DeepSeek 批量分析错因，输出具体描述
- **错题本**：跨考聚合、模块筛选、乱序计时答题
- **行动指南**：送分题杀手 / 不该放弃的题 / 投入产出 Top5
- **AI 备考顾问**：多会话对话 + 个性化题组生成
- **申论批改**：AI 评分（内容/结构/语言）+ 素材库
- **笔记 + 链接**：备考笔记管理 + 自定义学习链接
- **暗色模式**：夜间刷题护眼

## 📋 项目结构

```
fenbi-review-assistant/
├── backend/                  # FastAPI 后端
│   ├── main.py               # 入口 + CORS + 路由注册
│   ├── db.py                 # 数据库依赖注入
│   ├── api/
│   │   ├── exams.py          # 模考列表/详情/抓取
│   │   ├── questions.py      # 题目更新/错题本/薄弱题型
│   │   ├── diagnose.py       # AI诊断(SSE)/诊断列表/确认
│   │   ├── insights.py       # 模块概览/错误分布/对比/KP详情/行动指南
│   │   ├── chat.py           # 多会话管理/AI对话/题组生成
│   │   ├── shenlun.py        # 申论抓取/作答/批改/素材库
│   │   └── notes.py          # 笔记CRUD/链接管理
│   └── requirements.txt
├── frontend/                 # React + TypeScript 前端
│   └── src/pages/
│       ├── Dashboard.tsx     # 仪表盘 + 抓取
│       ├── ExamReview.tsx    # 模考复盘（双视图+答题卡）
│       ├── WrongBank.tsx     # 错题本
│       ├── Insights.tsx      # 知识洞察 + 行动指南
│       ├── AIChat.tsx        # AI 顾问（多会话+气泡）
│       ├── Shenlun.tsx       # 申论练习
│       └── Notes.tsx         # 笔记 + 链接
├── utils/                    # Python 工具库（共用）
│   ├── db.py                 # SQLite 操作
│   ├── analysis.py           # 统计分析
│   └── llm.py                # LLM 调用
├── fetch.py                  # 数据抓取（CLI）
├── app.py                    # Streamlit 旧版（保留）
├── data/
│   ├── reports/              # 抓取报告
│   └── knowledge_base.db     # SQLite 知识库
├── skills/
│   └── error_diagnosis.md    # 诊断 Skill
└── config.yaml               # 配置文件（Cookie/API Key）

```

## 🚀 快速开始

### 1. 环境准备

Python 3.10+ / Node.js 18+

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install
```

### 2. 配置

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

### 3. 启动

```bash
# 终端1：后端
uvicorn backend.main:app --port 8000 --reload

# 终端2：前端
cd frontend && npm run dev
```

打开 `http://localhost:5173`

### 4. 移动端访问

```bash
# 安装 ngrok 后
ngrok http 8501  # Streamlit
# 或
ngrok http 5173  # React 前端
```

## 📊 考试类型支持

| 类型 | routecs | 支持 |
|------|---------|------|
| 行测 | xingce | ✅ |
| 职测 | szyfzc | ✅ |
| 申论 | shenlun | ✅ (材料+AI批改) |
| 公基 | - | 待开发 |
| 专业科目 | - | 待开发 |

## 📄 许可

MIT License
