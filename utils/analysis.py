"""统计与诊断逻辑模块

提供以下核心功能：
- 知识点到模块的自动归类
- 时间异常度计算
- 连续错题检测
- 蒙对识别
- 难度评估
- 初始化与增量分析报告生成
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Optional

# ======================== 考试类型配置 ========================

# 支持的考试类型及其模块定义（预留扩展接口）
EXAM_TYPE_CONFIG = {
    '行测': {
        'modules': ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析'],
        'name_patterns': ['行测', '行政职业能力', '省考', '国考', '模考大赛', '公务员录用'],
    },
    '职测': {
        'modules': ['言语理解与表达', '数量关系', '判断推理', '资料分析', '常识判断'],
        'name_patterns': ['职业能力测试', '职测', '三支一扶', '事业单位联考'],
    },
    '申论': {
        'modules': ['归纳概括', '综合分析', '提出对策', '贯彻执行', '文章写作'],
        'name_patterns': ['申论'],
    },
    '公共基础知识': {
        'modules': ['政治理论', '法律常识', '经济常识', '管理常识', '公文写作', '人文历史', '科技地理'],
        'name_patterns': ['公基', '公共基础', '事业单位', '综合知识'],
    },
    '专业科目': {
        'modules': [],  # 随 keypoints 动态识别
        'name_patterns': ['专业科目', '财会', '计算机', '法律专业', '公安'],
    },
}


def detect_exam_type(exam_name: str) -> str:
    """根据试卷名称自动识别考试类型。

    Args:
        exam_name: 试卷名称

    Returns:
        str: 考试类型（行测/申论/公共基础知识/专业科目），默认为行测
    """
    for exam_type, config in EXAM_TYPE_CONFIG.items():
        for pat in config['name_patterns']:
            if pat in exam_name:
                return exam_type
    return '行测'  # 兜底


# ======================== 模块归类 ========================

# 模块关键词映射表：按优先级从高到低匹配
# 注意：字典遍历顺序即匹配优先级，排在前面先匹配
# 扩展考试类型时，只需在 EXAM_TYPE_CONFIG 中注册，然后在此处补充模块关键词
MODULE_KEYWORDS = {
    "资料分析": [
        "增长率", "增长量", "比重", "倍数", "平均数", "年均增长",
        "综合分析", "综合资料", "基期", "现期", "同比", "环比",
        "拉动增长", "贡献率", "指数", "翻番", "百分点",
        "图表", "统计图", "折线图", "柱状图", "饼图",
        "年均增速", "年均增长量", "混合增速", "间隔增速",
        "两期比重", "基期比重", "比重差", "比重变化",
        "倍数与翻番", "平均数的增长量", "平均数的增长率",
        "容斥", "多部分", "拉动…增长", "贡献率",
        "进出口", "贸易", "进口", "出口",
        "文字资料", "统计表", "综合材料",
        "简单加减", "加减计算", "现期比重",
    ],
    "数量关系": [
        "方程", "不定方程", "排列组合", "概率", "几何",
        "行程", "工程", "合作", "浓度", "牛吃草", "容斥", "抽屉",
        "数列", "最值", "利润", "年龄", "钟表", "植树",
        "方阵", "鸡兔", "盈亏", "日期", "周期", "余数",
        "等差数列", "等比数列", "分段计费", "空瓶换酒",
        "均值不等式", "三元", "极值", "约数", "倍数特性",
        "整除", "奇偶", "质合", "代入排除",
        "和差倍比", "完工", "给工", "给效率", "给具体",
        "统筹", "分堆", "平均速度", "相遇", "追及",
        "比值计算",
    ],
    "言语理解与表达": [
        "言语", "阅读理解", "逻辑填空", "语句表达", "语序",
        "主旨", "意图", "细节", "标题", "衔接", "下文",
        "成语", "实词", "虚词", "混搭", "语境",
        "片段", "篇章", "病句", "歧义", "修辞",
        "态度", "词语理解", "代词", "语句排序",
        "语句填空", "承接叙述", "道理启示",
        "关联词", "转折", "因果", "对策", "词的辨析",
        "感情色彩", "词义侧重", "搭配对象", "前后呼应",
        "主题词", "问法", "接语", "横线", "分述句",
        "语法", "框架题", "拆词", "首句",
    ],
    "判断推理": [
        "判断", "图形", "定义", "类比", "逻辑",
        "翻译", "真假", "加强", "削弱", "前提",
        "归纳", "解释", "评价", "结构相似",
        "必然性", "可能性", "选言", "假言", "直言",
        "三段论", "论证", "平行结构",
        "位置类", "样式类", "数量类", "属性类", "重构类",
        "空间", "六面体", "三视图", "截面图", "立体拼合",
        "关联关系", "并列关系", "对应关系", "形象表达",
        "补充论据", "方式目的", "确定顺序", "拆桥",
        "日常结论", "属性规律", "对称", "黑白块",
        "集合", "捆绑", "位置规律", "平移", "主客体",
        "因果关系", "手段目的", "论证结构",
        "样式规律", "数量规律", "语义关系", "搭桥",
        "一真", "原因结果", "必要条件", "假设",
        "确定信息", "遍历", "加减同异", "黑白运算",
        "拆分",
    ],
    "常识判断": [
        "常识", "历史", "地理", "科技", "生物", "化学",
        "物理", "医学", "农业", "航天", "计算机",
        "文学", "文化", "艺术", "哲学", "宗教",
        "中国古代", "中国近代", "世界史", "省情",
        "天文", "气象", "节气", "民俗",
        "诉讼法", "重要事件",
        "法律", "民法典", "刑法", "宪法", "行政法",
        "民法", "法规", "条例", "普查", "人口",
        "时政", "科技成就", "新年贺词", "两会",
        "中央农村工作", "政府督查", "十四五",
    ],
    "政治理论": [
        "政治", "文件", "会议", "政策", "法律", "宪法",
        "行政法", "刑法", "民法", "法规", "条例",
        "时政", "二十大", "十九大", "二十大报告", "十九届",
        "政府工作报告", "一号文件", "中央经济工作",
        "国家安全", "外交", "军事", "国防",
        "建设", "经济", "民生", "生态", "党建",
        "唯物", "史观",
    ],
}


# 题型关键词映射表（模块 → 题型 → 关键词）
# 只有存在明确子类型的模块才需要细分
QUESTION_TYPE_KEYWORDS = {
    "言语理解与表达": {
        "逻辑填空": [
            "实词填空", "成语填空", "混搭填空", "前后呼应",
            "词的辨析", "感情色彩", "词义侧重", "程度轻重",
            "搭配对象", "关联词", "转折", "因果", "对策", "并列",
            "横线", "拆词",
        ],
        "阅读理解": [
            "主题词", "细节判断", "标题填入", "分述句",
            "问法", "代词", "框架题", "态度", "词语理解",
            "主旨", "意图", "道理启示", "言语理解",
        ],
        "语句表达": [
            "接语", "语句填空", "语句表达", "语句排序",
            "确定首句", "确定顺序", "确定捆绑", "病句",
            "语法关系", "下文", "衔接",
        ],
    },
    "判断推理": {
        "图形推理": [
            "属性规律", "黑白块", "空间类", "位置规律", "位置类",
            "特殊规律", "数量规律", "数量类", "样式规律", "样式类",
            "图形推理", "平移", "旋转", "对称", "遍历",
            "加减同异", "黑白运算", "六面体", "截面图",
            "三视图", "立体拼合", "重构类",
        ],
        "定义判断": [
            "单定义", "多定义", "主客体",
        ],
        "类比推理": [
            "逻辑关系", "语义关系", "关联关系", "对应关系",
            "形象表达", "解释说明", "语法关系", "集合",
            "并列关系", "全同关系", "包容关系", "交叉关系",
            "因果关系", "方式目的", "手段目的",
        ],
        "逻辑判断": [
            "论证", "削弱", "加强", "前提", "论据", "论点",
            "拆桥", "搭桥", "日常结论", "集合推理",
            "真假推理", "真假", "一真", "解释", "评价",
            "归纳", "假设", "必要条件", "原因结果",
            "确定顺序", "确定信息", "确定捆绑", "从确定",
            "拆分思维", "捆绑",
            "翻译", "假言", "直言", "选言", "三段论",
            "必然性", "可能性", "平行结构", "结构相似",
            "他因", "大前提",
        ],
    },
    "数量关系": {
        "数学运算": [
            "利润", "排列", "概率", "几何", "行程", "工程",
            "方程", "数列", "最值", "和差", "计算", "比值",
            "函数", "统筹", "同素", "合作", "完工",
            "给工", "给具体", "给效率", "速度", "相遇", "追及",
        ],
    },
    "资料分析": {
        "计算比较": [
            "增长率", "增长量", "比重", "倍数", "平均数",
            "基期", "现期", "计算", "比较", "简单加减",
            "综合资料", "文字资料", "统计图", "图表",
            "进口", "出口", "贸易", "综合", "年均",
        ],
    },
    "常识判断": {
        "科技常识": [
            "物理", "化学", "生物", "科技", "计算机",
        ],
        "人文常识": [
            "文学", "文化", "艺术", "哲学", "宗教", "民俗",
        ],
        "历史地理": [
            "历史", "中国古代", "中国近代", "世界史",
            "地理", "天文", "气象", "节气",
        ],
        "法律常识": [
            "法律", "诉讼法", "法规",
        ],
        "生活常识": [
            "生活", "医学", "农业", "航天",
        ],
        "其他常识": [
            "省情", "重要事件",
        ],
    },
    "政治理论": {
        "时政会议": [
            "会议", "文件", "二十大", "十九大", "政府工作报告",
            "一号文件", "中央经济工作",
        ],
        "经济政策": [
            "经济", "宏观", "微观", "市场", "贸易",
        ],
        "党建法治": [
            "政治", "党建", "宪法", "法律", "行政法", "刑法",
            "民法", "法规", "条例", "国家安全",
        ],
        "社会生态": [
            "民生", "社会建设", "生态", "文化",
        ],
        "外交国防": [
            "外交", "军事", "国防",
        ],
        "哲学思想": [
            "唯物", "史观", "辩证法", "新思想",
        ],
        "其他建设": ["建设"],
    },
}


def classify_question_type(point_name: str, module: str) -> str:
    """根据知识点名称和所属模块，归类到具体题型。

    Args:
        point_name: 知识点名称
        module: 所属模块名

    Returns:
        str: 题型名称，无法归类时返回模块名本身
    """
    type_map = QUESTION_TYPE_KEYWORDS.get(module, {})
    if not type_map:
        return module

    for qtype, keywords in type_map.items():
        for kw in keywords:
            if kw in point_name:
                return qtype

    return module  # 兜底：返回模块名


def classify_module(keypoint_names: list[str]) -> dict[str, list[str]]:
    """根据知识点名称列表，归类到对应模块。

    每个知识点名可能匹配多个模块关键词，取第一个匹配的模块。
    无法归类的知识点保留原名，模块标记为"其他"。

    Args:
        keypoint_names: 知识点名称列表，如 ["一般增长率", "综合资料"]

    Returns:
        dict: {"模块名": ["知识点1", "知识点2"], ...}
    """
    result = defaultdict(list)

    for name in keypoint_names:
        matched = False
        for module, keywords in MODULE_KEYWORDS.items():
            for kw in keywords:
                if kw in name:
                    result[module].append(name)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            result["其他"].append(name)

    return dict(result)


# ======================== 难度评估 ========================

def assess_difficulty(global_correct_ratio: Optional[float]) -> str:
    """根据全站正确率评估难度等级。

    Args:
        global_correct_ratio: 全站正确率百分比（如 20.59 表示 20.59%）

    Returns:
        str: 'easy' / 'medium' / 'hard'
    """
    if global_correct_ratio is None:
        return "medium"  # 默认中等
    if global_correct_ratio >= 80:
        return "easy"
    elif global_correct_ratio >= 30:
        return "medium"
    else:
        return "hard"


# ======================== 蒙对识别 ========================

def is_guessed_correct(
    status: int,
    time_spent_sec: Optional[float],
    global_correct_ratio: Optional[float],
    llm_opinion: Optional[dict] = None,
) -> bool:
    """判断一道答对的题是否为蒙对。

    满足以下任一条件即判定为蒙对：
    a. 正确且用时 < 5 秒
    b. 正确且全站正确率 < 30% 且用时 < 20 秒
    c. LLM 辅助判断认为语义关联性极低

    Args:
        status: 1=正确, -1=错误
        time_spent_sec: 做题用时
        global_correct_ratio: 全站正确率
        llm_opinion: LLM 辅助判断结果 {"is_guessed": bool, ...}

    Returns:
        bool: 是否为蒙对
    """
    if status != 1:
        return False

    # 条件 a
    if time_spent_sec is not None and time_spent_sec < 5:
        return True

    # 条件 b: 归一化后 0.3 对应 30%
    if (global_correct_ratio is not None and global_correct_ratio < 0.3
            and time_spent_sec is not None and time_spent_sec < 20):
        return True

    # 条件 c: LLM 辅助判断
    if llm_opinion and llm_opinion.get('is_guessed'):
        return True

    return False


# ======================== 时间异常度 ========================

def compute_time_anomaly(
    time_spent_sec: Optional[float],
    module_avg_time: float,
    global_avg_time: float,
    module_question_count: int,
) -> tuple[bool, float]:
    """计算时间异常度并判断是否为异常。

    公式：time_anomaly_ratio = time_spent_sec / avg_module_time
    当模块题数 < 5 时，使用全卷平均用时替代。

    Args:
        time_spent_sec: 本题用时
        module_avg_time: 该模块平均用时
        global_avg_time: 全卷平均用时
        module_question_count: 该模块总题数

    Returns:
        tuple[bool, float]: (是否超时, 异常比值)
    """
    if time_spent_sec is None or time_spent_sec <= 0:
        return False, 1.0

    reference_time = module_avg_time if module_question_count >= 5 else global_avg_time
    if reference_time <= 0:
        return False, 1.0

    ratio = time_spent_sec / reference_time
    is_anomaly = ratio > 1.5
    return is_anomaly, ratio


# ======================== 连续错题检测 ========================

def detect_persistent_weak_points(
    db,
    min_consecutive: int = 2,
    max_exams: int = 10,
) -> list[dict]:
    """检测跨考试持续薄弱的知识点。

    分析所有模考的错题数据，找出在连续多次考试中都出现
    错误的知识点（表明是真正需要关注的薄弱环节）。

    Args:
        db: KnowledgeDB 实例
        min_consecutive: 最少连续考试次数阈值
        max_exams: 最多分析最近几次考试

    Returns:
        list[dict]: [{point_name, module, question_type, streak, exams: [...], ...}, ...]
    """
    import json
    import os

    # 获取所有考试，按日期升序
    exams = db.get_exam_records()
    if len(exams) < 2:
        return []
    exams = list(reversed(exams))  # 升序：最早 → 最新
    exams = exams[-max_exams:]  # 只分析最近 N 次

    # 为每次考试构建错题知识点集合
    exam_kp_errors = []  # [{"exam_name": ..., "date": ..., "wrong_kps": set()}]
    for exam in exams:
        report_path = exam.get('report_path', '')
        if not os.path.exists(report_path):
            continue

        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                questions = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # 兼容新旧格式
        if isinstance(questions, dict):
            questions = questions.get('questions', questions.get('data', []))
        if not isinstance(questions, list):
            continue

        wrong_kps = set()
        for q in questions:
            if q.get('status') == -1:  # 答错
                for kp in q.get('keypoints', []):
                    kp_name = kp.get('name', '')
                    if kp_name:
                        wrong_kps.add(kp_name)

        if wrong_kps:  # 至少有错题才纳入分析
            exam_kp_errors.append({
                'exam_name': exam.get('exam_name', ''),
                'date': exam.get('exam_date', ''),
                'wrong_kps': wrong_kps,
            })

    if len(exam_kp_errors) < min_consecutive:
        return []

    # 归类知识点到模块和题型
    all_kps = set()
    for ek in exam_kp_errors:
        all_kps.update(ek['wrong_kps'])
    module_map = classify_module(list(all_kps))
    kp_to_module = {}
    kp_to_qtype = {}
    for mod, names in module_map.items():
        for n in names:
            kp_to_module[n] = mod
            kp_to_qtype[n] = classify_question_type(n, mod)

    # 检测每个知识点的连续出错情况
    results = []
    for kp_name in all_kps:
        # 构建该知识点在各次考试中的表现
        streak_records = []  # [(exam_name, date, is_wrong)]
        for ek in exam_kp_errors:
            streak_records.append((ek['exam_name'], ek['date'], kp_name in ek['wrong_kps']))

        # 找最长连续错误段
        best_streak = 0
        best_slice = []
        current_streak = 0
        current_slice = []

        for exam_name, date, is_wrong in streak_records:
            if is_wrong:
                current_streak += 1
                current_slice.append({'exam_name': exam_name, 'date': date})
            else:
                if current_streak > best_streak:
                    best_streak = current_streak
                    best_slice = list(current_slice)
                current_streak = 0
                current_slice = []

        # 末尾检查
        if current_streak > best_streak:
            best_streak = current_streak
            best_slice = list(current_slice)

        if best_streak >= min_consecutive:
            mod = kp_to_module.get(kp_name, '其他')
            results.append({
                'point_name': kp_name,
                'module': mod,
                'question_type': kp_to_qtype.get(kp_name, mod),
                'streak': best_streak,
                'exams': best_slice,
            })

    # 按连续次数降序
    results.sort(key=lambda r: -r['streak'])
    return results


# ======================== 报告解析 ========================

def parse_report(file_path: str) -> list[dict]:
    """解析 merged_report.json 文件。

    兼容旧格式（裸列表）和新格式（含元数据的 dict）。

    Args:
        file_path: JSON 文件路径

    Returns:
        list[dict]: 题目列表（新格式会将 exam_date 注入每题的 _exam_date 字段）
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        questions = data.get('questions', data.get('data', []))
        # 新格式：元数据注入到每道题
        exam_date = data.get('exam_date', '')
        for q in questions:
            if exam_date and not q.get('_exam_date'):
                q['_exam_date'] = exam_date
        return questions
    return []


def extract_exam_info(questions: list[dict]) -> dict:
    """从题目列表中提取模考基本信息。

    Returns:
        dict: {exam_name, exam_date, total_questions, correct_questions, total_time}
    """
    if not questions:
        return {
            'exam_name': '未知试卷',
            'exam_date': datetime.now().strftime('%Y-%m-%d'),
            'total_questions': 0,
            'correct_questions': 0,
            'total_time': 0.0,
        }

    # 从第一题的 source 提取试卷名
    first_source = questions[0].get('source', '')
    # 格式如: "2026上半年省考第十三季行测模考大赛（深圳卷）第96题"
    exam_name_match = re.match(r'^(.*?)第\d+题', first_source)
    exam_name = exam_name_match.group(1) if exam_name_match else '未知试卷'

    total = len(questions)
    correct = sum(1 for q in questions if q.get('status') == 1)
    total_time = sum(q.get('time_spent_sec', 0) or 0 for q in questions)

    # 推断日期：优先用 JSON 中的真实考试日期，其次目录时间戳
    exam_date = questions[0].get('_exam_date', '') if questions else ''
    if not exam_date:
        exam_date = datetime.now().strftime('%Y-%m-%d')

    return {
        'exam_name': exam_name,
        'exam_date': exam_date,
        'total_questions': total,
        'correct_questions': correct,
        'total_time': total_time,
    }


# ======================== 报告生成 ========================

def generate_init_report(db) -> str:
    """生成初始化后的「初始能力画像」Markdown 报告。

    Args:
        db: KnowledgeDB 实例

    Returns:
        str: Markdown 格式报告
    """
    modules = db.get_modules_summary()
    weak_points = db.get_weak_points(limit=10)
    time_anomaly = db.get_time_anomaly_points(limit=5)
    accuracy_gap = db.get_global_accuracy_gap(limit=10)
    guessed_count = db.get_guessed_correct_count()
    error_dist = db.get_error_type_distribution()

    lines = ["# 📊 初始能力画像\n"]

    # 1. 各模块正确率
    lines.append("## 一、各模块正确率与用时\n")
    lines.append("| 模块 | 总题数 | 正确率 | 平均用时 |")
    lines.append("|------|--------|--------|----------|")
    for m in modules:
        lines.append(
            f"| {m['module']} | {m['total_q']} | {m['accuracy']:.1%} | "
            f"{m['avg_time']:.1f}秒 |"
        )

    # 用时稳定性（知识点级别的标准差）
    all_points = db.get_all_knowledge_points()
    lines.append("\n### 用时稳定性（按模块）\n")
    module_times = defaultdict(list)
    for kp in all_points:
        if kp['total_occurrences'] > 0:
            avg = kp['total_time_sec'] / kp['total_occurrences']
            module_times[kp['module']].append(avg)
    lines.append("| 模块 | 知识点数 | 平均用时 | 用时标准差 |")
    lines.append("|------|----------|----------|------------|")
    for mod, times in sorted(module_times.items()):
        if len(times) >= 2:
            avg = sum(times) / len(times)
            variance = sum((t - avg) ** 2 for t in times) / (len(times) - 1)
            std = variance ** 0.5
            lines.append(f"| {mod} | {len(times)} | {avg:.1f}秒 | {std:.1f}秒 |")

    # 2. 高频错误知识点 Top 10
    lines.append("\n## 二、高频错误知识点 Top 10\n")
    lines.append("| 排名 | 知识点 | 错误/总数 | 正确率 |")
    lines.append("|------|--------|-----------|--------|")
    for i, w in enumerate(weak_points, 1):
        lines.append(
            f"| {i} | {w['full_label']} | "
            f"{w['error_count']}/{w['total_occurrences']} | "
            f"{w['accuracy']:.1%} |"
        )

    # 3. 用时异常知识点 Top 5
    lines.append("\n## 三、用时异常知识点 Top 5\n")
    lines.append("| 排名 | 知识点 | 平均用时 | 偏离度 |")
    lines.append("|------|--------|----------|--------|")
    for i, t in enumerate(time_anomaly, 1):
        lines.append(
            f"| {i} | {t['full_label']} | "
            f"{t['avg_time']:.1f}秒 | "
            f"{t['deviation_ratio']:.2f}x |"
        )

    # 4. 全站正确率偏离度
    lines.append("\n## 四、全站正确率偏离度分析\n")
    lines.append("> 以下是你正确率远低于全站正确率的知识点：\n")
    lines.append("| 排名 | 知识点 | 你的正确率 | 全站平均正确率 | 差距 |")
    lines.append("|------|--------|------------|----------------|------|")
    for i, g in enumerate(accuracy_gap, 1):
        lines.append(
            f"| {i} | {g['full_label']} | "
            f"{g['my_accuracy']:.1%} | "
            f"{g['avg_global_accuracy']:.1%} | "
            f"{g['gap']:.1%} |"
        )

    # 5. 蒙对题
    lines.append(f"\n## 五、蒙对题总数：{guessed_count}\n")
    if guessed_count > 0:
        lines.append("> 蒙对题详情请在 Web 界面查看。\n")

    # 6. 跨考持续薄弱知识点
    lines.append("\n## 六、跨考持续薄弱知识点\n")
    persistent = detect_persistent_weak_points(db)
    if persistent:
        for pp in persistent[:10]:
            exam_list = ' → '.join(e['exam_name'][:12] for e in pp['exams'])
            qt = pp.get('question_type', '') or pp['module']
            lines.append(
                f"- **{pp['point_name']}**（{pp['module']} → {qt}）："
                f"连续 {pp['streak']} 次考试出错 ({exam_list})"
            )
    else:
        lines.append("> 考试次数不足，暂无法分析跨考薄弱趋势。\n")

    # 7. 错误类型分布
    if error_dist:
        lines.append("\n## 七、错误类型分布\n")
        total = sum(error_dist.values())
        lines.append("| 错误类型 | 次数 | 占比 |")
        lines.append("|----------|------|------|")
        for et, cnt in sorted(error_dist.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {et} | {cnt} | {cnt/total:.1%} |")

    return '\n'.join(lines)


def generate_incremental_report(
    current_exam: dict,
    previous_exam: dict = None,
    db=None,
) -> str:
    """生成增量分析报告（含新旧对比）。

    Args:
        current_exam: 当前模考信息
        previous_exam: 上一份模考信息（可选）
        db: KnowledgeDB 实例

    Returns:
        str: Markdown 格式报告
    """
    lines = [f"# 📋 模考复盘报告\n"]
    lines.append(f"**试卷：{current_exam.get('exam_name', '未知')}**\n")
    lines.append(f"**日期：{current_exam.get('exam_date', '未知')}**\n")
    lines.append(
        f"**成绩：{current_exam.get('correct_questions', 0)}/"
        f"{current_exam.get('total_questions', 0)} "
        f"（{current_exam.get('correct_questions', 0)/max(current_exam.get('total_questions', 1), 1):.1%}）**\n"
    )

    # 对比上次
    if previous_exam:
        prev_correct = previous_exam.get('correct_questions', 0)
        prev_total = previous_exam.get('total_questions', 1)
        curr_correct = current_exam.get('correct_questions', 0)
        curr_total = current_exam.get('total_questions', 1)

        prev_rate = prev_correct / max(prev_total, 1)
        curr_rate = curr_correct / max(curr_total, 1)
        change = curr_rate - prev_rate

        lines.append(f"**上次正确率：** {prev_rate:.1%}")
        lines.append(f"**本次正确率：** {curr_rate:.1%}")
        direction = "↑ 提升" if change > 0 else ("↓ 下降" if change < 0 else "→ 持平")
        lines.append(f"**变化：** {direction} {abs(change):.1%}\n")

    # 附上初始化报告的所有洞察
    if db:
        base_report = generate_init_report(db)
        lines.append("\n---\n")
        lines.append(base_report)

    return '\n'.join(lines)


# ======================== 批量初始化分析 ========================

def process_report_for_init(
    file_path: str,
    db,
    diagnose_errors: bool = False,
) -> dict:
    """处理单份报告，进行初始化入库和分析。

    包括：
    1. 解析报告
    2. 更新 exam_records
    3. 逐题更新 knowledge_points 和 question_analysis
    4. 检测连续错题
    5. （可选）调用 LLM 诊断错误类型

    Args:
        file_path: merged_report.json 路径
        db: KnowledgeDB 实例
        diagnose_errors: 是否调用 LLM 诊断（初始化时通常为 False）

    Returns:
        dict: 处理统计信息
    """
    questions = parse_report(file_path)
    if not questions:
        return {'success': False, 'error': '报告为空或无法解析'}

    # 提取模考信息
    exam_info = extract_exam_info(questions)
    exam_info['report_path'] = file_path

    # 从目录名提取实际抓取时间戳（格式：YYYY-MM-DD_HH-MM-SS_...）
    dir_name = os.path.basename(os.path.dirname(file_path))
    ts_match = re.match(r'(\d{4}-\d{2}-\d{2})_\d{2}-\d{2}-\d{2}', dir_name)
    if ts_match:
        exam_info['exam_date'] = ts_match.group(1)

    # 检查是否已入库
    if db.exam_exists(file_path):
        return {'success': False, 'error': f'报告已入库：{file_path}'}

    # 插入模考记录
    exam_type = detect_exam_type(exam_info['exam_name'])
    db.insert_exam_record(
        report_path=file_path,
        exam_name=exam_info['exam_name'],
        exam_date=exam_info['exam_date'],
        total_questions=exam_info['total_questions'],
        correct_questions=exam_info['correct_questions'],
        total_time_sec=exam_info['total_time'],
        exam_type=exam_type,
    )

    # 归类知识点 → 模块
    all_kp_names = []
    for q in questions:
        for kp in q.get('keypoints', []):
            all_kp_names.append(kp.get('name', ''))
    module_map = classify_module(list(set(all_kp_names)))

    # 构建反向索引：知识点名 → 模块名
    name_to_module = {}
    for mod, names in module_map.items():
        for n in names:
            name_to_module[n] = mod

    # 计算模块平均用时（用于时间异常检测）
    module_times = defaultdict(list)
    for q in questions:
        kps = q.get('keypoints', [])
        for kp in kps:
            mod = name_to_module.get(kp.get('name', ''), '其他')
            if q.get('time_spent_sec'):
                module_times[mod].append(q['time_spent_sec'])

    module_avg_times = {}
    for mod, times in module_times.items():
        module_avg_times[mod] = sum(times) / len(times) if times else 0

    global_avg_time = sum(
        q.get('time_spent_sec', 0) or 0 for q in questions
    ) / max(len(questions), 1)

    # 逐题处理
    for q in questions:
        qk = q.get('key', '')
        kps = q.get('keypoints', [])
        status = q.get('status', 0)
        is_correct = status == 1
        time_spent = q.get('time_spent_sec')
        global_ratio_raw = q.get('global_correct_ratio')
        # 归一化为 0~1 小数（原始数据为百分比如 68.5 表示 68.5%）
        global_ratio = global_ratio_raw / 100.0 if global_ratio_raw is not None else None

        # 难度评估（assess_difficulty 接受百分比值）
        difficulty = assess_difficulty(global_ratio_raw)

        # 主模块（取第一个知识点对应的模块）
        primary_kp_name = kps[0].get('name', '') if kps else '未知'
        primary_module = name_to_module.get(primary_kp_name, '其他')

        # 蒙对识别
        guessed = is_guessed_correct(status, time_spent, global_ratio)

        # 时间异常
        mod_avg = module_avg_times.get(primary_module, global_avg_time)
        mod_count = len(module_times.get(primary_module, []))
        is_time_anom, time_ratio = compute_time_anomaly(
            time_spent, mod_avg, global_avg_time, mod_count
        )

        # 写入 question_analysis
        db.upsert_question_analysis({
            'report_key': file_path,
            'question_key': qk,
            'is_correct': is_correct,
            'time_spent_sec': time_spent,
            'global_correct_ratio': global_ratio,
            'error_type': None,
            'is_guessed_correct': guessed,
            'is_time_anomaly': is_time_anom,
            'user_marked': q.get('user_marked', False),
            'your_answer': q.get('your_answer', ''),
            'correct_answer': q.get('correct_answer', ''),
            'difficulty': difficulty,
            'user_note': '',
            'source': q.get('source', ''),
        })

        # 更新所有相关知识点
        for kp in kps:
            kp_name = kp.get('name', '未知')
            mod = name_to_module.get(kp_name, '其他')
            qtype = classify_question_type(kp_name, mod)
            db.upsert_knowledge_point(
                module=mod,
                point_name=kp_name,
                is_correct=is_correct,
                time_spent=time_spent or 0.0,
                error_type=None,  # 初始化时不填错误类型
                difficulty=difficulty,
                global_accuracy=global_ratio,
                exam_date=exam_info['exam_date'],
                question_type=qtype,
            )

    return {
        'success': True,
        'exam_name': exam_info['exam_name'],
        'total_questions': exam_info['total_questions'],
        'correct_questions': exam_info['correct_questions'],
    }


def process_report_for_analyze(
    file_path: str,
    db,
    diagnose_errors: bool = True,
) -> dict:
    """处理单份新报告，执行增量分析。

    与 process_report_for_init 类似，但增加了：
    - 错误类型的 LLM 诊断（若启用）
    - 生成待确认诊断列表
    - 蒙对/超时/连续错题的完整标记

    Args:
        file_path: merged_report.json 路径
        db: KnowledgeDB 实例
        diagnose_errors: 是否调用 LLM 诊断

    Returns:
        dict: 处理结果
    """
    result = process_report_for_init(file_path, db, diagnose_errors=False)

    if not result.get('success'):
        return result

    if not diagnose_errors:
        return result

    # 批量诊断错题
    from .llm import diagnose_error

    questions = parse_report(file_path)
    wrong_questions = [q for q in questions if q.get('status') == -1]

    diagnoses = []
    for q in wrong_questions:
        try:
            diag = diagnose_error(
                content=q.get('content', ''),
                options=q.get('options', []),
                your_answer=str(q.get('your_answer', '')),
                correct_answer=str(q.get('correct_answer', '')),
                solution=q.get('solution', ''),
                keypoints=q.get('keypoints', []),
                time_spent_sec=q.get('time_spent_sec'),
            )
            db.insert_pending_diagnosis(
                question_key=q.get('key', ''),
                report_path=file_path,
                error_type=diag.get('error_type', '其他'),
                confidence=diag.get('confidence', 0.0),
                explanation=diag.get('explanation', ''),
            )
            diagnoses.append({
                'question_key': q.get('key', ''),
                **diag,
            })
        except Exception as e:
            diagnoses.append({
                'question_key': q.get('key', ''),
                'error_type': '其他',
                'confidence': 0.0,
                'explanation': f'诊断失败：{str(e)}',
            })

    result['diagnoses'] = diagnoses
    result['pending_count'] = len(diagnoses)
    return result


def generate_confirmation_sheet(db, report_path: str) -> str:
    """生成标签确认单（Markdown 格式）。

    Args:
        db: KnowledgeDB 实例
        report_path: 报告路径

    Returns:
        str: Markdown 格式的确认单
    """
    pending = db.get_pending_diagnoses(report_path)

    if not pending:
        return "✅ 没有待确认的诊断项。"

    lines = [f"# 📝 错因诊断确认单\n"]
    lines.append(f"共 {len(pending)} 项待确认\n")

    for i, p in enumerate(pending, 1):
        qa = db.get_question_by_key(p['question_key'])
        q_info = ""
        if qa:
            q_info = (
                f"（你的答案：{qa.get('your_answer', '?')}，"
                f"正确答案：{qa.get('correct_answer', '?')}）"
            )

        lines.append(f"### {i}. {p['question_key']} {q_info}")
        lines.append(f"- **AI 建议类型：** {p['error_type']}")
        lines.append(f"- **置信度：** {p['confidence']:.0%}")
        lines.append(f"- **理由：** {p['explanation']}")
        lines.append(f"- **操作：** ⬜ 接受 / ✏️ 修改为：______\n")

    return '\n'.join(lines)


def _extract_qnum(source: str) -> int:
    """从 source 字段提取题号。"""
    m = re.search(r'第(\d+)题', source or '')
    return int(m.group(1)) if m else 9999


def sort_by_qnum(items: list[dict], key_field: str = 'source') -> list[dict]:
    """按题号排序（API 返回顺序是模块分组，不是题号序）。"""
    return sorted(items, key=lambda x: _extract_qnum(x.get(key_field, '')))


# ======================== 模块时间预算 ========================

# 标准考场时间分配（按 120 分钟行测为基准）
# 每题用时参考真实考场策略，而非机械平均
STANDARD_TIME_BUDGET_120 = {
    '常识判断':         {'sec_per_q': 35,  'pct': 0.08},   # ~10 min / 15-20题
    '政治理论':         {'sec_per_q': 40,  'pct': 0.10},   # ~12 min / 15-20题
    '言语理解与表达':   {'sec_per_q': 52,  'pct': 0.29},   # ~35 min / 40题
    '数量关系':         {'sec_per_q': 70,  'pct': 0.12},   # ~15 min / 12-15题
    '判断推理':         {'sec_per_q': 55,  'pct': 0.29},   # ~35 min / 35-40题
    '资料分析':         {'sec_per_q': 75,  'pct': 0.20},   # ~25 min / 20题
}


def analyze_module_timing(questions: list[dict]) -> list[dict]:
    """分析各模块的用时情况（基于真实考场策略）。

    评估维度：
    - 是否超预算（严格）
    - 是否挤压了其他模块时间
    - 是否存在战略性放弃（用时极少 + 高错误率）

    Returns:
        list[dict]: [{module, question_count, actual_min, budget_min, ratio, verdict, advice}, ...]
    """
    from collections import defaultdict

    # 按模块统计
    mod_data = defaultdict(lambda: {'count': 0, 'total_sec': 0.0, 'wrong': 0})
    for q in questions:
        kps = q.get('keypoints', [])
        kp_names = [k.get('name', '') for k in kps]
        mod_map = classify_module(list(set(kp_names))) if kp_names else {}
        mod = next(iter(mod_map.keys()), None)
        if not mod:
            continue  # 无法归类的不参与时间分析
        mod_data[mod]['count'] += 1
        mod_data[mod]['total_sec'] += q.get('time_spent_sec', 0) or 0
        if q.get('status') == -1:
            mod_data[mod]['wrong'] += 1

    # 每题预算固定，不随考试时长缩放（一道资料分析题在哪都是 ~75 秒）
    results = []
    total_budget_sec = 0

    for mod in ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析']:
        data = mod_data.get(mod)
        if not data or data['count'] == 0:
            continue
        budget_cfg = STANDARD_TIME_BUDGET_120.get(mod, {'sec_per_q': 50, 'pct': 0.1})
        budget_sec = budget_cfg['sec_per_q'] * data['count']
        total_budget_sec += budget_sec
        actual = data['total_sec']
        ratio = actual / max(budget_sec, 1)
        wrong_rate = data['wrong'] / max(data['count'], 1)

        # 判定
        if ratio > 1.4:
            verdict = '🔴 严重超时'
            advice = '拖慢全局节奏，练习时严格限时，超时就跳'
        elif ratio > 1.15:
            verdict = '🟡 偏慢'
            advice = '有优化空间，检查是否在某几题上纠结过久'
        elif ratio < 0.3 and wrong_rate > 0.6:
            verdict = '⚠️ 疑似全蒙'
            advice = '用时极短但错很多，可能战略性放弃，需补基础'
        elif ratio < 0.5:
            verdict = '🟢 偏快'
            advice = '时间充裕，检查正确率是否匹配'
        else:
            verdict = '✅ 正常'
            advice = '节奏合理'

        results.append({
            'module': mod,
            'question_count': data['count'],
            'actual_min': actual / 60,
            'budget_min': budget_sec / 60,
            'ratio': ratio,
            'wrong_rate': wrong_rate,
            'verdict': verdict,
            'advice': advice,
        })

    return results


def diagnose_report_errors(db, report_path: str) -> dict:
    """对已入库报告的所有未诊断错题运行 LLM 批量诊断。

    5 题一批，大幅降低 API 调用成本（~80% 节省）。

    Args:
        db: KnowledgeDB 实例
        report_path: 已入库报告的路径

    Returns:
        dict: {diagnosed: int, skipped: int, errors: int, batches: int}
    """
    from .llm import diagnose_error_batch

    # 获取该报告的所有错题
    questions = db.get_questions_by_report(report_path)
    wrong_qs = [q for q in questions if not q.get('is_correct', True)]

    # 解析原始报告以获取题目内容
    import json as _json
    import os as _os
    raw_questions = {}
    if _os.path.exists(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                raw_list = _json.load(f)
            if isinstance(raw_list, dict):
                raw_list = raw_list.get('questions', raw_list.get('data', []))
            if isinstance(raw_list, list):
                raw_questions = {q.get('key', ''): q for q in raw_list}
        except (_json.JSONDecodeError, IOError):
            pass

    # 筛选未诊断的错题
    to_diagnose = []
    skipped = 0
    for q in wrong_qs:
        if q.get('error_type') and q['error_type'] != '其他':
            skipped += 1
            continue
        rq = raw_questions.get(q.get('question_key', ''), {})
        # 推断模块（用于批量诊断的加权提示）
        kps = rq.get('keypoints', [])
        kp_names = [k.get('name', '') for k in kps]
        mod_map = classify_module(list(set(kp_names))) if kp_names else {}
        mod = next(iter(mod_map.keys()), '') if mod_map else ''
        to_diagnose.append({**rq, 'question_key_db': q.get('question_key', ''), 'module': mod})

    if not to_diagnose:
        return {'diagnosed': 0, 'skipped': skipped, 'errors': 0, 'batches': 0}

    # 按题号排序（API 返回是按模块分组的，不是题号序）
    to_diagnose = sort_by_qnum(to_diagnose, key_field='source')

    # 5 题一批
    BATCH_SIZE = 5
    batches = [to_diagnose[i:i+BATCH_SIZE] for i in range(0, len(to_diagnose), BATCH_SIZE)]

    diagnosed = 0
    errors = 0

    for batch in batches:
        try:
            results = diagnose_error_batch(batch)

            for q, diag in zip(batch, results):
                qk = q.get('question_key_db') or q.get('key', '')
                db.insert_pending_diagnosis(
                    question_key=qk,
                    report_path=report_path,
                    error_type=diag.get('error_type', '其他'),
                    confidence=diag.get('confidence', 0.0),
                    explanation=diag.get('explanation', ''),
                    specific_error=diag.get('specific_error', ''),
                )
                diagnosed += 1
        except Exception:
            errors += len(batch)

    return {
        'diagnosed': diagnosed,
        'skipped': skipped,
        'errors': errors,
        'batches': len(batches),
    }
