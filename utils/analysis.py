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
    '行测/职测': {
        'modules': ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析'],
        'name_patterns': ['行测', '行政职业能力', '省考', '国考', '模考大赛', '公务员录用',
                         '职业能力测试', '职测', '职业能力倾向测验', '事业单位联考', '三支一扶'],
    },
    '公基': {
        'modules': ['时事政治', '政治', '经济', '管理', '公文', '人文历史', '科技地理', '法律', '农业农村知识', '其他'],
        'name_patterns': ['综合知识', '公基', '公共基础', '公共基础知识'],
    },
    '申论': {
        'modules': ['归纳概括', '综合分析', '提出对策', '贯彻执行', '文章写作'],
        'name_patterns': ['申论'],
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
    return '行测/职测'  # 兜底


# ======================== 模块归类 ========================

# 模块关键词映射表：按优先级从高到低匹配
# 注意：字典遍历顺序即匹配优先级，排在前面先匹配
# 扩展考试类型时，只需在 EXAM_TYPE_CONFIG 中注册，然后在此处补充模块关键词
MODULE_KEYWORDS = {
    # ============ 行测/职测 模块 ============
    "资料分析": [
        "增长率", "增长量", "比重", "倍数", "平均数", "年均增长",
        "综合分析", "综合资料", "综合材料", "基期", "现期", "同比", "环比",
        "拉动增长", "贡献率", "指数", "翻番", "百分点",
        "图表", "统计图", "折线图", "柱状图", "饼图", "统计表",
        "年均增速", "年均增长量", "混合增速", "间隔增速",
        "两期比重", "基期比重", "比重差", "比重变化", "比重问题",
        "倍数与翻番", "倍数与比值", "平均数的增长量", "平均数的增长率",
        "平均数问题", "容斥", "多部分", "拉动…增长",
        "进出口", "贸易", "进口", "出口",
        "文字资料", "简单加减", "加减计算", "简单计算", "现期比重",
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
        "比值计算", "数学运算",
    ],
    "言语理解与表达": [
        "言语", "阅读理解", "逻辑填空", "语句表达", "语序",
        "主旨", "意图", "细节", "标题", "衔接", "下文",
        "成语", "实词", "虚词", "混搭", "语境",
        "片段", "片段阅读", "篇章", "病句", "歧义", "修辞",
        "态度", "词语理解", "代词", "语句排序",
        "语句填空", "承接叙述", "道理启示",
        "关联词", "转折", "因果", "对策", "词的辨析",
        "感情色彩", "词义侧重", "搭配对象", "前后呼应",
        "主题词", "问法", "接语", "横线", "分述句",
        "语法", "框架题", "拆词", "首句",
    ],
    "判断推理": [
        "判断", "图形", "定义", "类比", "逻辑",
        "图形推理", "定义判断", "类比推理", "逻辑判断",
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
        "确定信息", "遍历", "加减同异", "黑白运算", "拆分",
    ],
    "常识判断": [
        "常识", "历史", "地理", "科技", "生物", "化学",
        "物理", "医学", "农业", "航天",
        "文学", "文化", "艺术",
        "中国古代", "中国近代", "世界史", "省情",
        "天文", "气象", "节气", "民俗",
        "经济常识", "科技常识", "人文常识", "地理国情", "法律常识",
        # 行测常识判断也包含经济和法律类知识点，必须在公基关键词之前匹配
        "经济", "法律", "宪法", "刑法", "民法典", "民法", "行政法",
        "法规", "条例", "诉讼法", "劳动法",
        "宏观经济", "微观经济", "市场经济",
    ],
    "政治理论": [
        "政治理论", "马克思主义", "新思想", "时事政治", "毛中特",
        "文件", "会议", "政策",
        "二十大", "十九大", "二十大报告", "十九届",
        "政府工作报告", "一号文件", "中央经济工作",
        "国家安全", "外交", "军事", "国防",
        "唯物", "史观", "辩证法",
        "重要会议", "重要文件", "重要事件",
        "建设", "政治建设", "经济建设", "社会建设", "文化建设", "生态建设",
    ],

    # ============ 公基 模块 ============
    "时事政治": [
        "时政真题", "时政模拟题", "重要文件", "重要会议讲话",
        "重要事件", "时政",
    ],
    "政治": [
        "马克思主义哲学", "毛泽东思想概论", "中国特色社会主义理论体系",
        "党的基本知识", "道德", "科学社会主义",
        "哲学", "毛概", "中特", "党史", "党建",
    ],
    "经济": [
        "社会主义市场经济体制", "宏观经济", "微观经济",
        "市场经济", "经济体制",
    ],
    "管理": [
        "行政管理", "公共管理",
    ],
    "公文": [
        "公文", "公文的基本知识", "公文写作", "公文处理",
    ],
    "人文历史": [
        "历史常识", "文学常识", "文化常识", "人文", "历史",
        "中国古代史", "中国近代史", "世界历史",
    ],
    "科技地理": [
        "科技", "地理国情", "地理", "科技常识", "生物", "化学", "物理",
        "计算机基础知识",
    ],
    "法律": [
        "法理学", "宪法", "刑法", "民法典", "知识产权",
        "行政法", "行政法与行政诉讼法", "经济法", "商法",
        "劳动法", "劳动法与社会保障法", "程序法", "诉讼法",
        "民法", "法规", "条例",
    ],
    "农业农村知识": [
        "基层治理", "三农政策法规", "三农", "农业农村", "乡村振兴",
    ],
    "其他": [
        "计算机基础知识",
    ],
}


# 题型关键词映射表（模块 → 题型 → 关键词）
# 只有存在明确子类型的模块才需要细分
QUESTION_TYPE_KEYWORDS = {
    # ============ 行测/职测 题型 ============
    "言语理解与表达": {
        "逻辑填空": [
            "实词填空", "成语填空", "混搭填空", "前后呼应",
            "词的辨析", "感情色彩", "词义侧重", "程度轻重",
            "搭配对象", "关联词", "转折", "因果", "对策", "并列",
            "横线", "拆词", "逻辑填空",
        ],
        "片段阅读": [
            "主题词", "细节判断", "标题填入", "分述句",
            "问法", "代词", "框架题", "态度", "词语理解",
            "主旨", "意图", "道理启示", "片段阅读",
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
            "单定义", "多定义", "主客体", "定义判断",
        ],
        "类比推理": [
            "逻辑关系", "语义关系", "关联关系", "对应关系",
            "形象表达", "解释说明", "语法关系", "集合",
            "并列关系", "全同关系", "包容关系", "交叉关系",
            "因果关系", "方式目的", "手段目的", "类比推理",
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
            "他因", "大前提", "逻辑判断",
        ],
    },
    "数量关系": {
        "数学运算": [
            "利润", "排列", "概率", "几何", "行程", "工程",
            "方程", "数列", "最值", "和差", "计算", "比值",
            "函数", "统筹", "同素", "合作", "完工",
            "给工", "给具体", "给效率", "速度", "相遇", "追及",
            "数学运算",
        ],
    },
    "资料分析": {
        "简单计算": ["简单计算", "简单加减", "加减计算"],
        "基期与现期": ["基期", "现期"],
        "增长率": ["增长率", "年均增速", "混合增速", "间隔增速", "平均数的增长率"],
        "增长量": ["增长量", "年均增长量", "平均数的增长量"],
        "比重问题": ["比重", "比重问题", "两期比重", "基期比重", "比重差", "比重变化", "现期比重"],
        "平均数问题": ["平均数", "平均数问题"],
        "倍数与比值相关": ["倍数", "倍数与翻番", "倍数与比值"],
        "文字资料": ["文字资料"],
        "统计表": ["统计表"],
        "统计图": ["统计图", "图表", "折线图", "柱状图", "饼图"],
        "综合资料": ["综合资料", "综合材料", "综合分析"],
        "综合分析": ["综合分析"],
    },
    "常识判断": {
        "科技常识": ["物理", "化学", "生物", "科技", "科技常识"],
        "人文常识": ["文学", "文化", "艺术", "民俗", "人文常识"],
        "历史地理": ["历史", "中国古代", "中国近代", "世界史", "地理", "天文", "气象", "节气"],
        "法律常识": ["法律", "诉讼法", "法规", "法律常识"],
        "经济常识": ["经济常识", "宏观经济", "微观经济", "市场经济", "经济"],
        "地理国情": ["地理国情", "省情"],
    },
    "政治理论": {
        "马克思主义": ["马克思主义", "唯物", "史观", "辩证法", "哲学"],
        "新思想": ["新思想"],
        "时事政治": ["时政", "时事政治", "会议", "文件", "二十大", "十九大",
                     "政府工作报告", "一号文件", "中央经济工作", "重要会议", "重要文件", "重要事件"],
        "毛中特": ["毛中特", "毛泽东思想", "中特", "建设", "政治建设", "经济建设",
                  "社会建设", "文化建设", "生态建设", "党建"],
    },

    # ============ 公基 题型 ============
    "时事政治": {
        "时政真题": ["时政真题", "重要文件", "重要会议讲话", "重要事件"],
        "时政模拟题": ["时政模拟题"],
    },
    "政治": {
        "马克思主义哲学": ["马克思主义哲学", "唯物论", "辩证法", "认识论", "历史唯物主义"],
        "毛泽东思想概论": ["毛泽东思想概论", "毛概"],
        "中国特色社会主义理论体系": ["中国特色社会主义理论体系", "中特"],
        "新思想": ["新思想"],
        "党的基本知识": ["党的基本知识", "党史", "党建"],
        "道德": ["道德"],
        "科学社会主义": ["科学社会主义"],
    },
    "经济": {
        "社会主义市场经济体制": ["社会主义市场经济体制", "市场经济"],
        "宏观经济": ["宏观经济", "微观经济", "经济"],
    },
    "管理": {
        "行政管理": ["行政管理", "公共管理", "管理"],
    },
    "公文": {
        "公文的基本知识": ["公文", "公文的基本知识", "公文写作", "公文处理"],
    },
    "人文历史": {
        "历史常识": ["历史常识", "历史", "中国古代史", "中国近代史", "世界历史"],
        "文学常识": ["文学常识", "文学"],
        "文化常识": ["文化常识", "文化", "艺术", "民俗"],
        "其他（人文历史）": ["人文"],
    },
    "科技地理": {
        "科技": ["科技", "生物", "化学", "物理", "计算机"],
        "地理国情": ["地理国情", "地理"],
    },
    "法律": {
        "法理学": ["法理学"],
        "宪法": ["宪法"],
        "刑法": ["刑法"],
        "民法典": ["民法典", "民法"],
        "知识产权": ["知识产权"],
        "行政法与行政诉讼法": ["行政法", "行政法与行政诉讼法"],
        "经济法": ["经济法"],
        "商法": ["商法"],
        "劳动法与社会保障法": ["劳动法", "劳动法与社会保障法"],
        "程序法": ["程序法", "诉讼法"],
    },
    "其他": {
        "计算机基础知识": ["计算机基础知识"],
    },
    "农业农村知识": {
        "基层治理": ["基层治理"],
        "三农政策法规": ["三农政策法规", "三农", "农业农村", "乡村振兴"],
    },
}


def classify_question_type(point_name: str, module: str) -> str:
    """根据知识点名称和所属模块，归类到具体题型。

    Args:
        point_name: 知识点名称
        module: 所属模块名

    Returns:
        str: 题型名称，无法归类时返回"未归类"
    """
    type_map = QUESTION_TYPE_KEYWORDS.get(module, {})
    if not type_map:
        return "未归类"

    for qtype, keywords in type_map.items():
        for kw in keywords:
            if kw in point_name:
                return qtype

    return "未归类"  # 兜底：不再返回模块名


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
                confidence=diag.get('confidence', 0.0),
                explanation=diag.get('explanation', ''),
                specific_error=diag.get('specific_error', ''),
                countermeasure=diag.get('countermeasure', ''),
            )
            diagnoses.append({
                'question_key': q.get('key', ''),
                **diag,
            })
        except Exception as e:
            diagnoses.append({
                'question_key': q.get('key', ''),
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
        if p.get('specific_error'):
            lines.append(f"- **错因：** {p['specific_error']}")
        if p.get('countermeasure'):
            lines.append(f"- **对策：** {p['countermeasure']}")
        lines.append(f"- **置信度：** {p['confidence']:.0%}")
        lines.append(f"- **理由：** {p['explanation']}")
        lines.append(f"- **操作：** ⬜ 接受\n")

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


def analyze_module_timing(questions: list[dict], exam_order: list[str] = None) -> list[dict]:
    """分析各模块的用时情况（基于真实考场策略）。

    评估维度：
    - 是否超预算（严格）
    - 是否挤压了其他模块时间
    - 是否存在战略性放弃（用时极少 + 高错误率）
    - 按用户实际做题顺序分析连锁挤压

    Returns:
        list[dict]: [{module, question_count, actual_min, budget_min, ratio, verdict, advice}, ...]
    """
    from collections import defaultdict
    import os as _os, json as _json

    # 加载考试顺序
    if exam_order is None:
        config_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'user_config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = _json.load(f)
            exam_order = config.get('exam_order', ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析'])
        except Exception:
            exam_order = ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析']

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
    # 按用户实际做题顺序排列
    results = []
    total_budget_sec = 0

    ordered_mods = [m for m in exam_order if m in mod_data]
    # 补上没有出现在做题顺序中的模块
    for m in mod_data:
        if m not in ordered_mods:
            ordered_mods.append(m)

    for i, mod in enumerate(ordered_mods):
        data = mod_data[mod]
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
            'order': i + 1,  # 做题顺序中的位置
            'question_count': data['count'],
            'actual_min': actual / 60,
            'budget_min': budget_sec / 60,
            'ratio': ratio,
            'wrong_rate': wrong_rate,
            'verdict': verdict,
            'advice': advice,
        })

    return results


def diagnose_report_errors(db, report_path: str, cancel_event=None):
    """对已入库报告的所有未诊断错题运行 LLM 批量诊断。

    8 题一批，大幅降低 API 调用成本（~80% 节省）。
    生成器逐批 yield 进度事件，最终 yield status='done' 的汇总结果。

    Args:
        db: KnowledgeDB 实例
        report_path: 已入库报告的路径
        cancel_event: threading.Event，设置后中止后续批处理

    进度事件:  {'status': 'progress', 'current': int, 'total': int,
                'batches_done': int, 'total_batches': int}
    完成事件:  {'status': 'done', 'diagnosed': int, 'skipped': int,
                'errors': int, 'batches': int}
    取消事件:  {'status': 'cancelled', 'diagnosed': int, ...}
    """
    from .llm import diagnose_error_batch

    # 加载用户能力画像（用于个性化诊断）
    user_profile = generate_user_profile(db)

    # 清除该报告的旧诊断记录，防止重新诊断时重复累积
    db.clear_pending_diagnoses(report_path)

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

    # 收集待诊断的错题
    to_diagnose = []
    skipped = 0
    for q in wrong_qs:
        rq = raw_questions.get(q.get('question_key', ''), {})
        # 推断模块和题型（用于批量诊断和整体分析）
        kps = rq.get('keypoints', [])
        kp_names = [k.get('name', '') for k in kps]
        mod_map = classify_module(list(set(kp_names))) if kp_names else {}
        mod = next(iter(mod_map.keys()), '') if mod_map else ''
        qtype = classify_question_type(kp_names[0] if kp_names else '', mod) if kp_names else mod
        to_diagnose.append({**rq, 'question_key_db': q.get('question_key', ''), 'module': mod, 'question_type': qtype})

    if not to_diagnose:
        yield {'status': 'done', 'diagnosed': 0, 'skipped': skipped, 'errors': 0, 'batches': 0}
        return

    # 按题号排序（API 返回是按模块分组的，不是题号序）
    to_diagnose = sort_by_qnum(to_diagnose, key_field='source')

    # 8 题一批
    BATCH_SIZE = 5
    batches = [to_diagnose[i:i+BATCH_SIZE] for i in range(0, len(to_diagnose), BATCH_SIZE)]

    diagnosed = 0
    errors = 0
    all_diags: list[dict] = []  # 收集诊断结果用于整体分析

    for i, batch in enumerate(batches):
        # 检查取消信号
        if cancel_event and cancel_event.is_set():
            yield {
                'status': 'cancelled',
                'diagnosed': diagnosed,
                'skipped': skipped,
                'errors': errors,
                'batches': len(batches),
            }
            return

        try:
            results = diagnose_error_batch(batch, user_profile=user_profile)

            for q, diag in zip(batch, results):
                qk = q.get('question_key_db') or q.get('key', '')
                db.insert_pending_diagnosis(
                    question_key=qk,
                    report_path=report_path,
                    confidence=diag.get('confidence', 0.0),
                    explanation=diag.get('explanation', ''),
                    specific_error=diag.get('specific_error', ''),
                    countermeasure=diag.get('countermeasure', ''),
                )
                diagnosed += 1
                all_diags.append({
                    'module': q.get('module', '其他'),
                    'question_type': q.get('question_type', q.get('module', '其他')),
                    'specific_error': diag.get('specific_error', ''),
                })
        except Exception as e:
            import traceback
            err_msg = f"第{i+1}/{len(batches)}批失败：{e}"
            print(err_msg)
            traceback.print_exc()
            errors += len(batch)
            yield {'status': 'batch_error', 'msg': err_msg, 'batch': i+1}

        yield {
            'status': 'progress',
            'current': diagnosed + errors,
            'total': len(to_diagnose),
            'batches_done': i + 1,
            'total_batches': len(batches),
        }

    # 生成整体分析
    if diagnosed > 0:
        yield {'status': 'summary_start', 'msg': '正在生成整体分析...'}
        try:
            summary = generate_exam_summary(db, report_path, all_diags, user_profile)
            db.save_exam_summary(report_path, summary)
            yield {'status': 'summary', 'content': summary}
        except Exception as e:
            yield {'status': 'summary', 'content': f'整体分析生成失败：{e}'}

        # 预生成矛盾分析缓存（只刷新本次考试所属类型，不影响其他类型的缓存）
        try:
            exam_rec = db.get_exam_by_path(report_path)
            et = exam_rec.get("exam_type", "行测/职测") if exam_rec else None
            generate_contradiction_analysis(db, force=True, exam_type=et)
        except Exception:
            pass  # 矛盾分析失败不影响诊断主流程

    yield {
        'status': 'done',
        'diagnosed': diagnosed,
        'skipped': skipped,
        'errors': errors,
        'batches': len(batches),
    }


# ======================== 用户画像 + 整体分析 ========================

def generate_user_profile(db, force: bool = False) -> str:
    """基于历史数据生成用户能力画像。

    Args:
        db: KnowledgeDB 实例
        force: True 时强制重新生成，忽略缓存

    Returns:
        str: 用户画像文本（Markdown），无数据时返回空字符串
    """
    import os as _os
    profile_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'user_profile.md')

    if not force and _os.path.exists(profile_path):
        with open(profile_path, 'r', encoding='utf-8') as f:
            cached = f.read().strip()
            if cached:
                return cached

    from .llm import _get_client, _load_llm_config

    ctx = db.get_db_context_for_chat()
    exams = db.get_exam_records()
    if not ctx or len(exams) < 1:
        return ''

    user_prompt = f"""基于以下考生数据，生成一份简洁的能力画像：

{ctx}

请描述：
1. 整体能力定位与趋势
2. 优势模块与薄弱模块（基于正确率数据，不要列出具体错误类型或知识点标签）
3. 时间管理特点
4. 优先级最高的提升方向

要求：
- 客观、数据驱动、200-300字
- 禁止出现任何具体错误类型标签（如"概念混淆""计算失误"等）
- 禁止列出知识点名称
- 只讨论模块层面的表现。用中文。"""

    try:
        cfg = _load_llm_config()
        client = _get_client()
        resp = client.chat.completions.create(
            model=cfg.get('model', 'deepseek-chat'),
            messages=[
                {'role': 'system', 'content': '你是公考备考分析师。请基于考生的历史数据生成能力画像。禁止出现任何错误类型标签（如概念混淆、计算失误等）或知识点名称，只讨论模块层面的表现。'},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=500, temperature=0.3,
        )
        profile = resp.choices[0].message.content.strip()

        _os.makedirs(_os.path.dirname(profile_path), exist_ok=True)
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile)

        return profile
    except Exception:
        return ''


def generate_exam_summary(db, report_path: str, diagnoses: list[dict], user_profile: str = '') -> str:
    """生成整体复盘分析（在逐题诊断完成后调用）。

    分析粒度细化到模块下属题型（如 言语理解→逻辑填空），
    结合全站正确率区分「个人薄弱」和「题目本身偏难」。
    融入认知科学方法（元认知校准、测试效应、认知负荷）。

    Args:
        db: KnowledgeDB 实例
        report_path: 报告路径
        diagnoses: 诊断结果列表 [{'module': str, ...}, ...]
        user_profile: 用户能力画像文本

    Returns:
        str: 整体分析 Markdown 文本
    """
    from .llm import _get_client, _load_llm_config

    questions = parse_report(report_path)
    exam_info = extract_exam_info(questions)
    total_q = max(exam_info['total_questions'], 1)
    correct_q = exam_info['correct_questions']

    # ── 模块用时分析（含战略放弃检测）──
    timing_results = analyze_module_timing(questions)
    timing_summary = ''
    for t in timing_results:
        timing_summary += (
            f"\n- {t.get('order', '?')}.{t['module']}：{t['question_count']}题，"
            f"实际{t['actual_min']:.1f}分钟/预算{t['budget_min']:.1f}分钟，"
            f"错误率{t['wrong_rate']:.0%}，{t['verdict']}（{t['advice']}）"
        )

    # ── 模块→题型粒度分析（含全站正确率对比）──
    # 对每道题归类到 module + question_type
    qtype_stats: dict = {}  # key=(module, qtype) → {total, correct, global_acc_sum, global_acc_count}
    for q in questions:
        kps = q.get('keypoints', [])
        kp_names = [k.get('name', '') for k in kps]
        mod_map = classify_module(list(set(kp_names))) if kp_names else {}
        mod = next(iter(mod_map.keys()), '其他') if mod_map else '其他'
        qtype = classify_question_type(kp_names[0] if kp_names else '', mod) if kp_names else mod

        key = (mod, qtype)
        if key not in qtype_stats:
            qtype_stats[key] = {'total': 0, 'correct': 0, 'global_acc_sum': 0.0, 'global_acc_count': 0}
        qtype_stats[key]['total'] += 1
        if q.get('status') == 1:
            qtype_stats[key]['correct'] += 1
        gcr_raw = q.get('global_correct_ratio')
        if gcr_raw is not None:
            try:
                gcr = float(gcr_raw) / 100.0  # 归一化
                qtype_stats[key]['global_acc_sum'] += gcr
                qtype_stats[key]['global_acc_count'] += 1
            except (ValueError, TypeError):
                pass

    # 生成题型粒度分析文本
    qtype_lines = []
    for (mod, qtype), stats in sorted(qtype_stats.items()):
        if stats['total'] < 2:
            continue  # 样本太少不分析
        user_acc = stats['correct'] / max(stats['total'], 1)
        global_avg = stats['global_acc_sum'] / max(stats['global_acc_count'], 1) if stats['global_acc_count'] > 0 else None
        gap = user_acc - global_avg if global_avg is not None else None

        gap_note = ''
        if gap is not None:
            if gap < -0.15:
                gap_note = f'（全站{global_avg:.0%}，你{user_acc:.0%}，⚠️ 明显低于全站——个人薄弱点）'
            elif gap < -0.05:
                gap_note = f'（全站{global_avg:.0%}，你{user_acc:.0%}，略低于全站）'
            elif gap > 0.1:
                gap_note = f'（全站{global_avg:.0%}，你{user_acc:.0%}，高于全站）'
            else:
                gap_note = f'（全站{global_avg:.0%}，你{user_acc:.0%}，基本持平）'
        elif global_avg is None:
            gap_note = '（全站数据缺失）'

        qtype_lines.append(
            f"\n- {mod} → **{qtype}**：{stats['total']}题，"
            f"正确{stats['correct']}/{stats['total']}（{user_acc:.0%}）{gap_note}"
        )

    qtype_detail = '\n'.join(qtype_lines) if qtype_lines else '暂无题型粒度数据'

    # ── 汇总错题分布 ──
    mod_error_count: dict[str, int] = {}
    for d in diagnoses:
        mod = d.get('module', '其他')
        mod_error_count[mod] = mod_error_count.get(mod, 0) + 1

    diag_summary = ''
    for mod, cnt in mod_error_count.items():
        diag_summary += f"\n- {mod}：{cnt}道错题"

    profile_text = f"\n\n【考生能力画像】\n{user_profile}" if user_profile else ''

    user_prompt = f"""请对本次模考做整体复盘分析：

【考试信息】
- 试卷：{exam_info['exam_name']}
- 成绩：{correct_q}/{total_q}（{correct_q/total_q:.1%}）
- 总用时：{exam_info['total_time']/60:.1f}分钟

【模块用时分析（考场策略视角）】
{timing_summary}

【模块→题型粒度正确率（含全站对比）】
{qtype_detail}

【错题模块分布】
{diag_summary}
{profile_text}

请从以下角度深度分析（500-700字，Markdown格式）：

1. **题型级弱点诊断**：分析模块下属题型的正确率，区分两种情况——
   - 全站正确率也低 → 题目本身偏难或出题角度刁钻，不完全是你个人原因
   - 全站正确率高但你做错了 → 真正的个人薄弱环节，需要优先攻克
   举例：如果言语理解的「逻辑填空」全站正确率仅25%但你全错，说明逻辑填空本身就难；如果全站正确率70%但你全错，则说明这是你的短板。

2. **时间管理诊断**：分析各模块用时和错误率的关系——
   - 哪些模块用时远超预算但正确率没相应提高（可能在某几题上过度纠结）
   - 哪些模块用时极少且错误率极高（战略性放弃或全蒙，需补基础）
   - 哪些模块用时和正确率匹配合理

3. **认知负荷评估**（基于认知科学）：
   - 是否存在「高认知负荷低回报」的题型（用时多但正确率低的题型→建议优化解题策略或跳过）
   - 是否存在「测试效应」可利用的机会（哪些题型的错题在重新测试时可能快速提升）
   - 是否存在「元认知偏差」（用时很短但自信答对的题实际错了→说明对自己的判断不准确）

4. **与历史画像的关联**：问题是否延续了一贯模式，还是出现了新情况

5. **优先级建议**（按投入产出比排序）：
   - 优先攻克：全站正确率高但你做错的题型（最大提分空间）
   - 次要关注：全站正确率中等但你表现一般的题型
   - 保持观察：全站正确率低的难题（短期难突破，不宜投入过多）
   - 保持优势：你明显高于全站的题型

6. **具体行动**：3-4条可立即执行的学习建议（结合间隔重复、交错练习等认知科学方法）"""

    # 加载用户策略偏好
    user_strategy_text = _load_strategy_for_prompt()

    try:
        cfg = _load_llm_config()
        client = _get_client()
        resp = client.chat.completions.create(
            model=cfg.get('model', 'deepseek-chat'),
            messages=[
                {'role': 'system', 'content': (
                    '你是公考备考顾问，擅长结合认知科学（间隔重复、测试效应、认知负荷理论、'
                    '元认知校准、交错练习）进行学习诊断。\n'
                    + user_strategy_text + '\n'
                    '用中文，Markdown格式。分析必须精细到模块下属题型（如言语理解→逻辑填空），'
                    '结合全站正确率区分「题目难」和「个人弱」。\n'
                    '【语言规范】禁止使用笼统标签（如"认真做""可放弃型""粗心型"），必须说具体行为。'
                    '禁止建议"放弃某题型"。使用"策略优化"视角，不是"考前取舍"视角。'
                )},
                {'role': 'user', 'content': user_prompt},
            ],
            max_tokens=2500, temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f'整体分析生成失败：{e}'


def _load_strategy_for_prompt() -> str:
    """加载用户策略偏好用于 LLM prompt。"""
    import os as _os, json as _json
    config_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'user_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = _json.load(f)
        strategy = config.get('strategy', {})
        state = config.get('state_management', {})
        return (
            f'【考生策略（必须遵守）】备考阶段：{strategy.get("prep_phase", "")}。'
            f'备考周期：{strategy.get("prep_duration", "")}。'
            f'目标：{strategy.get("target_score", "")}分。'
            f'模块策略：{strategy.get("analysis_perspective", "")}。'
            f'工作状态：{state.get("work_status", "")}。'
            f'状态因素：{state.get("note", "")}。'
        )
    except Exception:
        return ''


# ======================== 矛盾分析（缓存） ========================

def _build_xingce_prompt(latest, exam_order, timing_matrix, qtype_detail, trends, cascade,
                         user_profile_text, strategy_text) -> tuple[str, str]:
    """构建行测/职测的矛盾分析 prompt。"""
    order_lines = []
    for i, mod in enumerate(exam_order):
        before = exam_order[:i]
        after = exam_order[i+1:]
        if before:
            order_lines.append(f"- {mod}(第{i+1}位)：只能被{', '.join(before)}挤压；可能挤压{', '.join(after) if after else '无'}")
        else:
            order_lines.append(f"- {mod}(第{i+1}位)：不可能被任何模块挤压；可能挤压{', '.join(after)}")
    order_note = (
        f"用户实际做题顺序：{' → '.join(exam_order)}\n\n"
        f"【硬约束】前序模块超时才可能挤压后序，后序模块绝不可能影响前序：\n"
        + '\n'.join(order_lines) +
        f"\n\n例如：资料分析(第2位)用时紧张 → 原因只能是言语理解(第1位)超时或资料分析自身难度大，"
        f"绝不可能是判断推理(第3位)导致的。"
    ) if exam_order else ""

    data_text = f"""## 最近考试：{latest['name']}（{latest['date']}）
成绩：{latest['correct_q']}/{latest['total_q']}（{latest['correct_q']/max(latest['total_q'],1)*100:.0f}%），用时{latest['total_time_min']}分钟
{order_note}

### 模块用时-正确率矩阵（按做题顺序）
{_fmt_dict_table(timing_matrix)}

### 题型粒度分析（含全站对比）
{_fmt_dict_table(qtype_detail)}

### 跨考试趋势（仅同类型考试比较）
{_fmt_trend_lines(trends) if trends else '仅1场考试，暂无趋势数据'}

### 连锁影响（已按做题顺序校验）
{_fmt_cascade_lines(cascade) if cascade else '未检测到明显的连锁影响'}"""

    system_prompt = f"""你是公考行测/职测备考策略专家。请对考生数据进行矛盾分析。

【考生背景】{user_profile_text[:800]}

【考生策略】{strategy_text}

核心概念：
- **主要矛盾**：不是"得分最低的模块"，而是制约全局的根源瓶颈。
- **矛盾的主要方面**：同一问题中起主导作用的方面（知识短板 vs 时间分配 vs 策略问题 vs 状态因素）。
- **矛盾的普遍性与特殊性**：全站都难=普遍性；你个人弱=特殊性（优先攻克）。

时间挤压方向铁律：前序超时才可能挤压后序，后序绝不可能影响前序。

【语言规范】
- 禁止笼统标签（"认真做""可放弃型""粗心型"），必须说具体行为
- 禁止建议"放弃某题型"，考生备考周期1年，不放弃任何模块
- 使用"策略优化"视角，不是"考前取舍"视角

分析要求：
1. 一针见血指出当前主要矛盾（具体到模块或题型）
2. 解释为什么它是主要矛盾
3. 矛盾的主要方面（知识短板 vs 时间分配 vs 策略问题 vs 状态因素）
4. 区分普遍性和特殊性矛盾
5. 结合1年备考周期和在职状态给长期建议"""

    return system_prompt, data_text


def _build_gongji_prompt(latest, timing_matrix, qtype_detail, trends,
                         user_profile_text, strategy_text) -> tuple[str, str]:
    """构建公基的矛盾分析 prompt——不涉及做题顺序和时间挤压。"""
    data_text = f"""## 最近考试：{latest['name']}（{latest['date']}）
成绩：{latest['correct_q']}/{latest['total_q']}（{latest['correct_q']/max(latest['total_q'],1)*100:.0f}%）

### 模块正确率矩阵
{_fmt_dict_table(timing_matrix)}

### 题型粒度分析（含全站对比）
{_fmt_dict_table(qtype_detail)}

### 跨考试趋势（仅同类型考试比较）
{_fmt_trend_lines(trends) if trends else '仅1场考试，暂无趋势数据'}"""

    system_prompt = f"""你是公基/综合知识备考策略专家。请对考生数据进行矛盾分析。

【考生背景】{user_profile_text[:800]}

【考生策略】{strategy_text}

公基考试特点（与行测完全不同）：
- 公基考察知识广度而非做题速度，时间压力通常不大
- 不存在"做题顺序挤压"问题，各模块独立性较强
- 核心矛盾通常是：知识储备的广度与深度之争、记忆效率与遗忘曲线的对抗、系统学习与碎片积累的平衡
- 部分模块（时事政治、法律）分值高、提分快，是投入产出比最高的方向

核心概念：
- **主要矛盾**：不是"得分最低的模块"，而是制约全局的知识体系短板。
- **矛盾的主要方面**：知识盲区 vs 记忆不牢 vs 理解偏差 vs 复习方法不当。
- **矛盾的普遍性与特殊性**：全站都难=该模块需要长期积累（如科技地理）；你个人弱=可以通过系统复习快速提升（如法律常识）。

【语言规范】
- 禁止笼统标签（"认真做""可放弃型"），必须说具体行为
- 禁止建议"放弃某模块"，考生备考周期1年，需要系统积累
- 使用"知识体系构建"视角，不是"考前突击"视角
- 结合在职备考的碎片时间特点给建议

分析要求：
1. 一针见血指出当前主要矛盾（具体到模块或题型），结合全站正确率区分"大家都难"和"你个人弱"
2. 解释为什么它是主要矛盾——它如何影响整体知识体系
3. 矛盾的主要方面：知识广度不够 vs 记忆不牢固 vs 理解深度不足
4. 按投入产出比排序改进方向（法律/时政通常ROI最高，科技地理需要长期积累）
5. 结合在职备考碎片时间特点，给出可执行的知识积累策略"""

    return system_prompt, data_text


# ======================== 矛盾分析（按类型缓存） ========================

def generate_contradiction_analysis(db, force: bool = False, exam_type: str = None) -> dict:
    """生成矛盾分析（按考试类型分别缓存）。

    行测/职测和公基各自独立缓存，诊断新考试时只刷新对应类型的分析。
    exam_type=None 时返回所有类型的分析，API 端点在响应中按类型分组。
    """
    import os as _os, json as _json

    exams = db.get_exam_records()
    if not exams:
        return {"error": "需要至少1场考试"}

    all_types = sorted(set(e.get("exam_type", "行测/职测") for e in exams))
    target_types = [exam_type] if exam_type else all_types

    results: dict = {}
    for et in target_types:
        type_key = et.replace("/", "").replace(" ", "_")
        cache_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', f'contradiction_cache_{type_key}.json')

        type_exams = [e for e in exams if e.get("exam_type", "行测/职测") == et]
        if not type_exams:
            continue
        latest_date = max(e.get("exam_date", "") for e in type_exams)

        if not force and _os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = _json.load(f)
                if cached.get("_latest_exam_date") == latest_date:
                    results[et] = cached
                    continue
            except Exception:
                pass

        type_result = _generate_contra_for_type(db, et, type_exams)
        results[et] = type_result

        try:
            _os.makedirs(_os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                _json.dump(type_result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    if exam_type:
        return results.get(exam_type, {"error": f"无{exam_type}类型的考试"})
    return results


def _generate_contra_for_type(db, exam_type: str, type_exams: list[dict]) -> dict:
    """为指定考试类型生成矛盾分析。"""
    import os as _os, json as _json
    from collections import defaultdict

    exams_sorted = sorted(type_exams, key=lambda e: e.get("exam_date", "") or "")
    latest_date = max(e.get("exam_date", "") for e in type_exams)

    # ── 数据收集 ──
    exam_data = []
    for exam in exams_sorted:
        rp = exam.get("report_path", "")
        if not _os.path.exists(rp):
            continue
        qs = db.get_questions_by_report(rp)
        with open(rp, "r", encoding="utf-8") as f:
            data = _json.load(f)
        raw_qs = data if isinstance(data, list) else data.get("questions", [])
        q_map = {q.get("key", ""): q for q in raw_qs if isinstance(q, dict)}

        mods: dict = {}
        for qa in qs:
            rq = q_map.get(qa.get("question_key", ""), {})
            kps = rq.get("keypoints", [])
            names = [k.get("name", "") for k in kps]
            mm = classify_module(list(set(names))) if names else {}
            mod = next(iter(mm.keys()), "其他") if mm else "其他"
            qtype = classify_question_type(names[0] if names else "", mod) if names else mod
            if mod not in mods:
                mods[mod] = {"total": 0, "correct": 0, "time": 0.0, "qtypes": {}}
            if qtype not in mods[mod]["qtypes"]:
                mods[mod]["qtypes"][qtype] = {"total": 0, "correct": 0, "global_sum": 0.0, "global_n": 0}
            mods[mod]["total"] += 1
            mods[mod]["time"] += qa.get("time_spent_sec", 0) or 0
            mods[mod]["qtypes"][qtype]["total"] += 1
            if qa.get("is_correct"):
                mods[mod]["correct"] += 1
                mods[mod]["qtypes"][qtype]["correct"] += 1
            gcr = qa.get("global_correct_ratio")
            if gcr is not None:
                mods[mod]["qtypes"][qtype]["global_sum"] += float(gcr) * 100
                mods[mod]["qtypes"][qtype]["global_n"] += 1

        for mod in mods:
            m = mods[mod]
            m["accuracy"] = round(m["correct"] / max(m["total"], 1) * 100, 1)
            m["avg_time"] = round(m["time"] / max(m["total"], 1), 1)
            for qt in m["qtypes"]:
                qd = m["qtypes"][qt]
                qd["accuracy"] = round(qd["correct"] / max(qd["total"], 1) * 100, 1)
                qd["global_avg"] = round(qd["global_sum"] / max(qd["global_n"], 1), 1) if qd["global_n"] > 0 else None

        exam_data.append({
            "name": (exam.get("exam_name", "") or "")[:30],
            "date": exam.get("exam_date", "") or "",
            "total_q": exam.get("total_questions", 0) or 0,
            "correct_q": exam.get("correct_questions", 0) or 0,
            "total_time_min": round((exam.get("total_time_sec", 0) or 0) / 60, 1),
            "modules": {m: {"accuracy": v["accuracy"], "avg_time": v["avg_time"],
                             "total": v["total"], "qtypes": v["qtypes"]}
                        for m, v in mods.items() if v["total"] >= 2},
        })

    if not exam_data:
        return {"error": "无有效考试数据"}

    latest = exam_data[-1]

    # ── 加载配置 ──
    exam_order = []
    config_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'user_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = _json.load(f)
        exam_order = config.get("exam_order", [])
    except Exception:
        pass

    def _budget(mod):
        b = {"常识判断": 35, "政治理论": 40, "言语理解与表达": 52,
             "数量关系": 70, "判断推理": 55, "资料分析": 75}
        return b.get(mod, 50)

    # ── timing_matrix（按做题顺序排列）──
    timing_matrix = []
    for i, mod in enumerate(exam_order):
        if mod in latest["modules"]:
            md = latest["modules"][mod]
            timing_matrix.append({
                "序号": i + 1, "模块": mod, "题数": md["total"], "正确率": md["accuracy"],
                "平均用时秒": md["avg_time"], "预算秒": _budget(mod),
                "超支比例": round(md["avg_time"] / max(_budget(mod), 1), 2),
            })
    for mod, md in latest["modules"].items():
        if mod not in exam_order:
            timing_matrix.append({
                "序号": 99, "模块": mod, "题数": md["total"], "正确率": md["accuracy"],
                "平均用时秒": md["avg_time"], "预算秒": _budget(mod),
                "超支比例": round(md["avg_time"] / max(_budget(mod), 1), 2),
            })

    # ── qtype_detail ──
    qtype_detail = []
    for mod, md in latest["modules"].items():
        for qt, qd in md["qtypes"].items():
            if qd["total"] < 2:
                continue
            gap = round(qd["accuracy"] - qd["global_avg"], 1) if qd["global_avg"] is not None else None
            qtype_detail.append({
                "模块": mod, "题型": qt, "题数": qd["total"],
                "你的正确率": qd["accuracy"], "全站正确率": qd["global_avg"],
                "差距": gap,
                "判定": "个人弱" if (gap is not None and gap < -10) else (
                    "题目难" if (gap is not None and gap > -10 and qd["global_avg"] is not None and qd["global_avg"] < 40) else "正常"),
            })

    # ── trends（已限定同类型考试）──
    trends = []
    if len(exam_data) >= 2:
        all_mods = set()
        for ed in exam_data:
            all_mods.update(ed["modules"].keys())
        for mod in sorted(all_mods):
            pts = []
            for ed in exam_data:
                if mod in ed["modules"]:
                    pts.append({"考试": ed["name"][:12], "日期": ed["date"], "正确率": ed["modules"][mod]["accuracy"]})
            if len(pts) >= 2:
                delta = pts[-1]["正确率"] - pts[0]["正确率"]
                trends.append({"模块": mod, "趋势": pts, "变化": round(delta, 1),
                               "方向": "↑提升" if delta > 5 else ("↓下降" if delta < -5 else "→持平")})

    # ── cascade（仅行测/职测适用，公基跳过）──
    cascade = []
    if exam_type != '公基':
        for i, mod in enumerate(exam_order):
            if mod not in latest["modules"]:
                continue
            md = latest["modules"][mod]
            time_ratio = md["avg_time"] / max(_budget(mod), 1)
            if time_ratio > 1.2 and md["accuracy"] < 65:
                victims = []
                for mod2 in exam_order[i+1:]:
                    if mod2 in latest["modules"]:
                        md2 = latest["modules"][mod2]
                        if md2["avg_time"] < _budget(mod2) * 0.75 and md2["accuracy"] < 70:
                            victims.append(f"{mod2}(仅{md2['avg_time']:.0f}秒/预算{_budget(mod2):.0f}秒)")
                if victims:
                    cascade.append({
                        "超时模块": f"{i+1}.{mod}", "超时倍数": round(time_ratio, 1),
                        "正确率": md["accuracy"], "可能挤压的模块": victims,
                        "分析": f"按做题顺序，{mod}(第{i+1}位)超时后，排在后面的模块被迫加速",
                    })

    # ── LLM 分析 ──
    ai_analysis = ""
    try:
        from .llm import _get_client, _load_llm_config
        cfg = _load_llm_config()
        client = _get_client()

        user_profile_text = ""
        profile_path = _os.path.join(_os.path.dirname(__file__), '..', 'data', 'user_profile.md')
        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                user_profile_text = f.read().strip()
        except Exception:
            pass

        strategy_text = _load_strategy_for_prompt()

        if exam_type == '公基':
            system_prompt, data_text = _build_gongji_prompt(
                latest, timing_matrix, qtype_detail, trends, user_profile_text, strategy_text)
        else:
            system_prompt, data_text = _build_xingce_prompt(
                latest, exam_order, timing_matrix, qtype_detail, trends, cascade,
                user_profile_text, strategy_text)

        resp = client.chat.completions.create(
            model=cfg.get("model", "deepseek-chat"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请对以下考生数据进行矛盾分析：\n\n{data_text}"},
            ],
            max_tokens=2000, temperature=0.5,
        )
        ai_analysis = resp.choices[0].message.content.strip()
    except Exception as e:
        ai_analysis = f"AI分析暂不可用：{e}"

    return {
        "_latest_exam_date": latest_date,
        "_exam_type": exam_type,
        "latest_exam": {"name": latest["name"], "date": latest["date"],
                        "score": f"{latest['correct_q']}/{latest['total_q']}"},
        "timing_matrix": timing_matrix,
        "qtype_detail": qtype_detail,
        "trends": trends,
        "cascade": cascade,
        "analysis": ai_analysis,
    }


def _fmt_dict_table(rows: list[dict]) -> str:
    if not rows:
        return "无数据"
    keys = list(rows[0].keys())
    header = "| " + " | ".join(str(k) for k in keys) + " |"
    sep = "|" + "|".join(["---" for _ in keys]) + "|"
    body = "\n".join("| " + " | ".join(str(r.get(k, "")) for k in keys) + " |" for r in rows)
    return header + "\n" + sep + "\n" + body


def _fmt_trend_lines(trends: list[dict]) -> str:
    lines = []
    for t in trends:
        pts_str = " → ".join(f"{p['考试']}({p['正确率']}%)" for p in t["趋势"])
        lines.append(f"- {t['模块']}：{pts_str} | {t['方向']}{t['变化']}%")
    return "\n".join(lines)


def _fmt_cascade_lines(cascade: list[dict]) -> str:
    lines = []
    for c in cascade:
        lines.append(f"- {c['超时模块']}超时{c['超时倍数']}倍（正确率仅{c['正确率']}%），可能挤压了：{', '.join(c['可能挤压的模块'])}")
        if c.get('分析'):
            lines.append(f"  → {c['分析']}")
    return "\n".join(lines)
