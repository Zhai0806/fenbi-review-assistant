```
我需要你帮我创建一个本地 Python 项目，项目名称叫 `fenbi-review-assistant`。该项目位于 `E:\1_fenbi-review-assistant`。这是一个基于认知科学理论的粉笔模考复盘工具，目标是帮我自动化分析行测/公基模考数据，建立长期的知识点掌握档案，并提供交互式咨询窗口。

### 一、项目背景
我已经可以通过脚本从粉笔网页版抓取并合并做题数据，生成结构化的 `merged_report.json`。该文件是一个数组，每个元素代表一道题，包含以下字段（实际字段已扩展）：
- `key`：题目唯一标识，如 "3_1_gtv1u"
- `id`：题目数字ID
- `content`：题干 HTML 文本
- `options`：选项列表（字符串数组，顺序对应 A/B/C/D）
- `correct_answer`：正确答案索引（"0"表示A，"1"表示B，依此类推）
- `solution`：官方解析 HTML 文本
- `keypoints`：知识点标签数组，如 `[{"id": 654272, "name": "一般增长率"}, {"id": 30237, "name": "综合资料"}]`
- `source`：试卷名称和题号，如 "2026上半年省考第十三季行测模考大赛（深圳卷）第96题"
- `your_answer`：我的答案索引（格式同 `correct_answer`）
- `time_spent_sec`：做题用时（秒），可能为 null
- `status`：1 表示正确，-1 表示错误
- `score_rate`：个人得分率（0或1）
- `global_correct_ratio`：全站正确率百分比，如 20.59（表示 20.59% 的考生答对此题），可能为 null
- `global_total_count`：全站答题总人数，可能为 null
- `user_marked`：布尔值，true 表示我在粉笔中手动标记过此题（收藏/标记）

抓取脚本 `fetch.py` 会通过粉笔接口自动生成该 JSON，并存入 `data/reports/` 目录。

### 二、项目目标与核心功能

#### 1. 一键抓取与配置复用
- 项目根目录下包含 `config.yaml` 作为配置文件，存储相对稳定的参数：`cookie`、`headers`（User-Agent, Referer 等）、`routes`（如 `xingce`）、`kav`, `av`, `hav` 等粉笔查询参数。
- 抓取脚本 `fetch.py` 支持两种调用方式：
  - `python fetch.py --exam-key 1_1_3jslr2e` （短 key）
  - `python fetch.py --url "完整的报告页面URL"`（从URL中自动提取短 key 和长 key）
- `fetch.py` 内部逻辑：
  1. 从 `config.yaml` 读取 cookie 和通用请求头。
  2. 通过命令行参数获取 `EXAM_KEY`，并自动请求 `getSolution` 接口，从返回的 `data.switchVO.requestKey` 字段提取长 key（`SOLUTION_KEY`）。
  3. 并发请求四个接口：`getSolution`、`static/solution`、`getMeta`（全站正确率）、`getMark`（用户标记）。
  4. 按之前讨论的合并逻辑，生成完整的 `merged_report.json`，保存至 `data/reports/YYYY-MM-DD_HH-MM-SS_<试卷名简称>/merged_report.json`。
- 如果 cookie 过期，只需更新 `config.yaml`，无需修改脚本。

#### 2. 初始化与知识库构建
- 项目支持一个命令：`python main.py init --data-dir <包含多份历史 merged_report.json 的文件夹>`。
- 程序将解析所有报告，抽取每道题的 `keypoints` 列表，构建**模块-知识点**复合标签（需从 `keypoints` 中的 `name` 字段推断模块归属，例如“一般增长率”归入“资料分析”，“重要文件”归入“政治理论”，若无法推断模块则保留原始标签）。
- 建立 SQLite 数据库 `knowledge_base.db`，包含以下表及字段：
  
  **表：`knowledge_points`**
  | 字段名 | 类型 | 说明 |
  |--------|------|------|
  | `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
  | `module` | TEXT NOT NULL | 模块名称，如“资料分析” |
  | `point_name` | TEXT NOT NULL | 知识点名称，如“一般增长率” |
  | `full_label` | TEXT UNIQUE NOT NULL | `模块-知识点` 组合，如“资料分析-一般增长率” |
  | `total_occurrences` | INTEGER DEFAULT 0 | 历史出现总次数 |
  | `correct_count` | INTEGER DEFAULT 0 | 历史正确次数 |
  | `total_time_sec` | REAL DEFAULT 0.0 | 总用时（秒） |
  | `time_squared_sum` | REAL DEFAULT 0.0 | 用时平方和，用于计算标准差 |
  | `error_type_distribution` | TEXT DEFAULT '{}' | JSON 字符串，存储错误类型计数字典，如 `{"计算失误":3,"概念混淆":2}` |
  | `difficulty_distribution` | TEXT DEFAULT '{}' | JSON 字符串，存储难度分布，如 `{"easy":4,"medium":6,"hard":2}` |
  | `global_accuracy_sum` | REAL DEFAULT 0.0 | 全站正确率累加（用于计算平均） |
  | `global_accuracy_count` | INTEGER DEFAULT 0 | 有全站正确率数据的题目数 |
  | `last_seen_date` | TEXT | 最近出现日期（YYYY-MM-DD） |
  | `trend_data` | TEXT DEFAULT '[]' | JSON 数组，存储最近N次正确率快照，如 `[1.0, 0.5, 0.0]` |

  **表：`exam_records`**（记录每次模考的整体信息）
  | 字段名 | 类型 | 说明 |
  |--------|------|------|
  | `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
  | `report_path` | TEXT NOT NULL | merged_report.json 完整路径 |
  | `exam_name` | TEXT | 试卷名称 |
  | `exam_date` | TEXT | 模考日期 |
  | `total_questions` | INTEGER | 总题数 |
  | `correct_questions` | INTEGER | 正确题数 |
  | `total_time_sec` | REAL | 总用时（秒） |

  **表：`question_analysis`**（单题分析记录，用于追溯）
  | 字段名 | 类型 | 说明 |
  |--------|------|------|
  | `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
  | `report_key` | TEXT | 外键关联 exam_records.report_path |
  | `question_key` | TEXT | 题目唯一标识 |
  | `is_correct` | BOOLEAN | 是否正确 |
  | `time_spent_sec` | REAL | 用时 |
  | `global_correct_ratio` | REAL | 全站正确率 |
  | `error_type` | TEXT | 错误类型（若错）；可空 |
  | `is_guessed_correct` | BOOLEAN | 是否蒙对（正确但用时极短且无充足理由） |
  | `is_time_anomaly` | BOOLEAN | 是否用时异常 |
  | `consecutive_error_group` | INTEGER | 连续错题组ID（用于标识连续错题段） |
  | `user_marked` | BOOLEAN | 是否被用户标记 |

- 初始化运行流程：
  1. 扫描给定文件夹，找到所有 `merged_report.json`（可递归）。
  2. 按模考日期排序，逐一解析。
  3. 对每道题，抽取知识点标签，更新 `knowledge_points` 表：
     - 增加 `total_occurrences` 和 `correct_count`（根据 status）。
     - 累加用时及平方。
     - 若题目错误，需要调用大模型诊断错误类型（见后），统计到 `error_type_distribution`。
     - 更新 `global_accuracy_sum` 和 `count`。
     - 更新 `last_seen_date`。
     - 将本次正确/错误（1/0）追加到 `trend_data`（最多保留最近10次）。
  4. 将每条题目分析写入 `question_analysis` 表，其中 `error_type` 暂存为 null，待后续 LLM 诊断后回填（初始化时可以只填基本字段，错误诊断留到增量阶段或批量后台补全）。
  5. 初始化完成后，输出“初始能力画像” Markdown 报告，内容包含：
     - 各模块正确率、平均用时、用时稳定性
     - 高频错误知识点 Top 10（按错误次数降序）
     - 用时异常知识点 Top 5（按用时偏离度降序）
     - 全站正确率偏离度分析（你的正确率远低于全站正确率的知识点列表）
     - 蒙对题总数及主要分布
     - 连续错题高发区域（连续错题≥3的片段）

#### 3. 增量分析（每次新模考）
- 命令：python main.py analyze --report <新 merged_report.json 路径>
- 处理流程：
1. 解析报告，备份到 data/reports/ 下标准目录。
2. 更新数据库基本字段（出现次数、正确次数、用时等）。
3. 对每道错题或异常题，调用 LLM 给出初步错误类型标签及置信度，存入一个临时表（或内存中），不直接修改 question_analysis。
4. 生成一份 标签确认单（Markdown 或 Streamlit 表单），列出所有待确认项：题目、你的答案、正确答案、AI 建议类型、置信度、快捷操作按钮（接受/修改）。
5.  经我确认或修改后，程序才将最终错误类型写入 question_analysis.error_type，并更新 knowledge_points 的 error_type_distribution。
6. 随后进行蒙对识别、超时标记、连续错题检测，生成最终复盘报告。
7. 增量报告包含与初始化相同的洞察，并增加“新弱点/复发/改善”对比。

#### 4. 大模型错因诊断（Skill 定义）
- 使用 DeepSeek v4 pro 模型（API 密钥已配置于环境，不必在提示词中写出）。调用方式采用项目配置文件中的模型名称和 base URL，通过 `openai` 兼容接口调用。
- 诊断输入：题目的 `content`、`options`、`your_answer`、`correct_answer`、`solution`、`keypoints`、`time_spent_sec`。
- 输出 JSON 格式：`{"error_type": "计算失误/公式用错/概念混淆/审题不清/时间不足蒙的/放弃/其他", "confidence": 0.85, "explanation": "简要诊断理由"}`
- 该 Skill 应以独立 Markdown 文件 `skills/error_diagnosis.md` 提供，写明系统提示词和输出格式要求，方便调整。
- 对于政治理论、常识等纯知识题，error_type 通常为“概念混淆”或“记忆盲区”；对于资料分析、数量关系，需结合解析推断是计算错还是公式错。
- 诊断结果写入 `question_analysis.error_type`，并更新 `knowledge_points.error_type_distribution`。

#### 5. 交互窗口（Streamlit Web 界面）
- 主命令：`streamlit run app.py`
- 界面布局三栏：
  - **左栏（复盘报告）**：
    - 选择框切换历史模考记录。
    - 显示所选模考的错题列表（表格形式），列包含：题号、知识点、你的答案、正确答案、用时、全站正确率、诊断错误类型（可编辑下拉框）、主观备注（文本输入框）。修改后自动保存到 `question_analysis` 表对应记录。
    - 蒙对题和超时题单独标签页展示。
    - 连续错题段高亮显示。
  - **中栏（知识库洞察）**：
    - 模块卡片（正确率、平均用时）。
    - 薄弱知识点排行榜（按正确率、错误次数排序）。
    - 用时异常知识点列表。
    - 错误类型分布饼图（概念混淆占比等）。
    - 难度-正确率矩阵（暂时可根据全站正确率分段：高正确率题你的正确率，低正确率题你的正确率）。
    - 历史趋势折线图：选择某一知识点，展示历次模考正确率变化。
  - **右栏（AI 聊天）**：
    - 基于历史知识库和当前报告，提供对话输入框。
    - 支持提问：例如“哪个模块最近下滑最严重？”、“给我生成5道关于增长率比较的练习题”、“帮我制定本周薄弱点攻克计划”等。
    - 聊天上下文可引用数据库统计信息，调用大模型生成个性化建议。
- 界面应美观、响应快，数据直接从 SQLite 读取，无需每次重新计算。

### 三、技术要求
- Python 3.10+，依赖：`requests`, `pyyaml`, `pandas`, `sqlite3`（内置）, `streamlit`, `plotly`（用于图表）, `openai`（用于调用DeepSeek兼容接口）。
- 项目结构：
fenbi-review-assistant/
├── config.yaml
├── fetch.py
├── main.py
├── app.py
├── skills/
│ └── error_diagnosis.md
├── data/
│ ├── reports/
│ └── knowledge_base.db
├── utils/
│ ├── db.py # 数据库操作封装
│ ├── analysis.py # 统计与诊断逻辑
│ └── llm.py # LLM调用封装
├── README.md
└── requirements.txt
- 代码注释详尽，关键函数有 docstring。
- 错误处理：网络请求重试、LLM 调用异常捕获、数据缺失默认值处理。

### 四、具体指标计算与处理细节（务必实现）
以下指标必须在分析层精确计算：

1. **时间异常度** (`time_anomaly_ratio`)  
 - 计算公式：`time_spent_sec / avg_module_time`，其中 `avg_module_time` 是从当前报告中该模块所有题目的用时平均值（剔除自身，或直接用中位数）。  
 - 如果该模块总题数 < 5，则使用全卷平均用时。  
 - 若比值 > 1.5，标记为“超时”；若比值 < 0.3 且正确，可能是蒙对。

2. **连续错题计数** (`consecutive_error_count`)  
 - 在分析每份报告时，按 `source` 字段解析题号（提取数字），排序后遍历状态。  
 - 连续错误数 ≥3 的序列生成一个组 ID（自增整数），存入 `question_analysis.consecutive_error_group`。  
 - 在界面中，这些题目标红显示，提示心态或知识点连锁崩溃。

3. **难度评估** (`difficulty`)  
 - 没有直接来源，综合以下规则自动判定：  
   - 全站正确率 ≥ 80% → `easy`  
   - 全站正确率 30%~80% → `medium`  
   - 全站正确率 < 30% → `hard`  
   - 若 `global_correct_ratio` 为空，则依据 `solution` 长度和 `content` 复杂度由 LLM 辅助打标（可选，优先用全站正确率）。  
 - 该难度存入 `knowledge_points.difficulty_distribution` 对应计数值。

4. **蒙对识别** (`is_guessed_correct`)  
 - 条件组合（满足任一即判定）：  
   a. `status==1` 且 `time_spent_sec < 5`  
   b. `status==1` 且 `global_correct_ratio < 30` 且 `time_spent_sec < 20`  
   c. `status==1` 但通过 LLM 检查选项间的语义关联性极低（调用诊断时附加判断）。  
 - 标记后写入 `question_analysis.is_guessed_correct`。

5. **错误类型分布更新**  
 - 当 LLM 返回错误类型后，在 `knowledge_points.error_type_distribution` 的 JSON 字段中给对应类型计数 +1。  
 - 前端展示时，可解析 JSON 绘制百分比堆积图。

6. **趋势数据**  
 - 每次模考后，将本次正确/错误（1/0）追加到 `trend_data` JSON 数组末尾。  
 - 保留最近 10 个数据点，用于绘制迷你折线图。

### 五、输出要求
请 Claude Code 一次性生成完整的项目文件，包括：
1. 所有 Python 源文件（`fetch.py`, `main.py`, `app.py`, `utils/db.py`, `utils/analysis.py`, `utils/llm.py`）。
2. `config.yaml` 模板（示例值用假数据）注：config.yaml已存在与工作环境不用再添加。
3. `skills/error_diagnosis.md` 文件。
4. `README.md` 包含安装步骤、配置指南、运行示例。
5. 一个测试用 `merged_report.json` 示例（可基于真实数据脱敏）。
确保代码可立即运行，逻辑严格遵循上述规范。

现在，请开始创建项目。
```