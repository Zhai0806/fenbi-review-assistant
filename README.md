# 📝 粉笔模考复盘助手 (fenbi-review-assistant)

基于认知科学理论的行测/公基模考数据分析工具。帮助你自动化分析粉笔模考数据，建立长期的知识点掌握档案，并提供交互式 AI 咨询。

## ✨ 功能特性

- **一键抓取**：从粉笔网页版自动抓取模考数据，合并生成结构化 JSON
- **知识库构建**：自动归类知识点到模块，建立 SQLite 知识库
- **智能诊断**：调用 DeepSeek 大模型诊断错题原因（计算失误/概念混淆/审题不清等）
- **蒙对识别**：自动识别"碰运气蒙对"的题目
- **连续错题检测**：标记连续错误段，提示心态或知识点连锁崩溃
- **时间异常分析**：识别超时或过快答题的题目
- **趋势追踪**：追踪每个知识点的历次正确率变化
- **Web 界面**：Streamlit 三栏布局，支持复盘浏览、知识洞察、AI 对话

## 📋 项目结构

```
fenbi-review-assistant/
├── config.yaml              # 配置文件（Cookie、请求头、LLM 参数）
├── fetch.py                 # 数据抓取脚本
├── main.py                  # CLI 入口（init / analyze / confirm）
├── app.py                   # Streamlit Web 界面
├── skills/
│   └── error_diagnosis.md   # 错因诊断 Skill 定义
├── data/
│   ├── reports/             # 抓取报告存放目录
│   │   └── sample/          # 示例数据
│   └── knowledge_base.db    # SQLite 知识库（运行后生成）
├── utils/
│   ├── __init__.py
│   ├── db.py                # 数据库操作封装
│   ├── analysis.py          # 统计与诊断逻辑
│   └── llm.py               # LLM 调用封装
├── requirements.txt
└── README.md
```

## 🚀 快速开始

### 1. 环境准备

- Python 3.10+
- 安装依赖：

```bash
pip install -r requirements.txt
```

### 2. 配置

编辑 `config.yaml`：

```yaml
# 粉笔网 Cookie（从浏览器复制）
fenbi:
  cookie: "你的完整Cookie字符串"

# LLM 配置
llm:
  model: "deepseek-chat"
  base_url: "https://api.deepseek.com/v1"
```

设置 DeepSeek API Key（通过环境变量）：

```bash
# Windows
set DEEPSEEK_API_KEY=sk-your-key-here

# Mac/Linux
export DEEPSEEK_API_KEY=sk-your-key-here
```

### 3. 抓取数据

```bash
# 方式1：使用短 key
python fetch.py --exam-key 1_1_3jslr2e

# 方式2：使用完整 URL
python fetch.py --url "https://spa.fenbi.com/..."
```

抓取的数据保存在 `data/reports/YYYY-MM-DD_HH-MM-SS_<试卷名>/merged_report.json`。

### 4. 初始化知识库

如果有历史模考数据，可以先批量导入：

```bash
python main.py init --data-dir data/reports/
```

这会扫描目录下所有 `merged_report.json`，建立知识库并生成「初始能力画像」报告。

### 5. 增量分析新模考

每次新模考后：

```bash
# 带 AI 诊断
python main.py analyze --report "data/reports/2026-06-16_10-30-00_xxx/merged_report.json"

# 跳过 AI 诊断（仅更新统计数据）
python main.py analyze --report "..." --no-diagnose
```

### 6. 启动 Web 界面

```bash
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`，三栏布局：

| 左栏 | 中栏 | 右栏 |
|------|------|------|
| 模考选择 | 模块正确率卡片 | AI 对话 |
| 错题列表（可编辑） | 薄弱知识点排行榜 | 快捷提问 |
| 蒙对/超时题 | 趋势折线图 | 备考建议 |
| 连续错题高亮 | 错误类型饼图 | |

## 📊 数据指标说明

### 时间异常度
`time_anomaly_ratio = 本题用时 / 该模块平均用时`
- > 1.5 → 标记为"超时"
- < 0.3 且正确 → 可能是蒙对

### 蒙对识别
满足任一条件即判定：
- 正确且用时 < 5 秒
- 正确且全站正确率 < 30% 且用时 < 20 秒
- LLM 辅助判断选项间无语义关联

### 难度评估
- 全站正确率 ≥ 80% → 简单 (easy)
- 全站正确率 30%-80% → 中等 (medium)
- 全站正确率 < 30% → 困难 (hard)

### 连续错题
题目按题号排序后，连续错误 ≥ 3 题即标记为一个连续错题组。

## 🔧 错误类型定义

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| 计算失误 | 知道方法但计算出错 | 资料分析、数量关系 |
| 公式用错 | 选错公式或不会列式 | 数量关系 |
| 概念混淆 | 混淆相近概念 | 言语成语、判断推理 |
| 审题不清 | 没看清题目要求 | 选非题看成选是题 |
| 时间不足蒙的 | 没时间认真做 | 用时极短且错误 |
| 记忆盲区 | 知识点未掌握 | 常识、时政、法律 |
| 放弃 | 战略性放弃 | 用时极短、题目偏难 |
| 其他 | 特殊情况 | - |

## 📝 模块分类规则

系统根据知识点名称关键词自动归类到以下模块：
- **资料分析**：增长率、增长量、比重、倍数、平均数等
- **数量关系**：方程、排列组合、概率、几何、行程、工程等
- **言语理解与表达**：阅读理解、逻辑填空、语句表达、病句等
- **判断推理**：图形推理、定义判断、类比推理、逻辑判断等
- **常识判断**：历史、地理、科技、生物、文化等
- **政治理论**：时政、法律、会议、文件、政策等

无法归类的知识点归入"其他"。

## 🧠 AI 对话示例

在 Web 界面右栏的 AI 聊天中，你可以问：

- "哪个模块最近下滑最严重？"
- "给我生成 5 道关于增长率比较的练习题"
- "帮我制定本周薄弱点攻克计划"
- "分析我的主要错误类型及改进建议"
- "资料分析部分的用时是否合理？有什么提速建议？"

## 📄 许可

MIT License
