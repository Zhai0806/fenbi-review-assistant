"""LLM 调用封装模块

使用 OpenAI 兼容接口调用 DeepSeek 模型进行错因诊断。
"""

import json
import os
import re
import time
from typing import Optional

import yaml
from openai import OpenAI


def _load_llm_config() -> dict:
    """从 config.yaml 加载 LLM 配置。"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('llm', {})


def _ensure_api_key(llm_config: dict) -> str:
    """确保 API Key 已配置，未配置时给出明确提示。"""
    api_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if not api_key:
        api_key = llm_config.get('api_key', '')
    if not api_key:
        raise ValueError(
            "DeepSeek API Key 未配置。请在 config.yaml 的 llm.api_key 中设置，"
            "或设置环境变量 DEEPSEEK_API_KEY"
        )
    return api_key


def _get_client() -> OpenAI:
    """获取 OpenAI 兼容客户端实例。

    API Key 读取优先级：
    1. 环境变量 DEEPSEEK_API_KEY
    2. config.yaml 中的 llm.api_key
    """
    llm_config = _load_llm_config()
    api_key = _ensure_api_key(llm_config)
    base_url = llm_config.get('base_url', 'https://api.deepseek.com/v1')
    return OpenAI(api_key=api_key, base_url=base_url)


def _load_diagnosis_skill() -> str:
    """加载错因诊断 Skill 的系统提示词。"""
    skill_path = os.path.join(os.path.dirname(__file__), '..', 'skills', 'error_diagnosis.md')
    try:
        with open(skill_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取 "## 系统提示词" 之后的全部内容作为 system prompt
        match = re.search(r'## 系统提示词\s*\n(.*)', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        # 如果没有找到二级标题，尝试提取正文
        return content.strip()
    except FileNotFoundError:
        # 回退到内置提示词
        return _default_system_prompt()


def _default_system_prompt() -> str:
    """当 skill 文件不存在时的默认系统提示词。"""
    return """你是一位资深的公考/行测辅导专家，擅长分析考生的错题原因。
请根据提供的题目信息，诊断考生答错这道题最可能的原因。

## 输出格式
请以 JSON 格式输出，包含以下字段：
- specific_error: 一句话说清错在哪
- countermeasure: 一句可执行的对策/技巧，告诉考生下次怎么避免
- confidence: 置信度，0.0~1.0 之间的浮点数
- explanation: 简要诊断理由，不超过100字

## 诊断规则
- 对于资料分析、数量关系类题目，优先考虑计算失误或公式用错
- 对于言语理解类题目，优先考虑审题不清或概念混淆
- 对于判断推理类题目，优先考虑概念混淆或审题不清
- 对于常识判断、政治理论类题目，优先考虑记忆盲区或概念混淆
- 如果用时明显不足（<10秒），可能是时间不足蒙的或放弃"""


def diagnose_error(
    content: str,
    options: list,
    your_answer: str,
    correct_answer: str,
    solution: str,
    keypoints: list,
    time_spent_sec: Optional[float],
    retry: int = 3,
) -> dict:
    """调用 LLM 诊断错题原因。

    Args:
        content: 题干 HTML 文本
        options: 选项列表
        your_answer: 考生答案索引
        correct_answer: 正确答案索引
        solution: 官方解析 HTML
        keypoints: 知识点标签列表 [{"id": ..., "name": ...}, ...]
        time_spent_sec: 做题用时（秒），可能为 None
        retry: 重试次数

    Returns:
        dict: {"specific_error": str, "countermeasure": str, "confidence": float, "explanation": str}
    """
    # 清理 HTML 标签，获取纯文本
    content_text = _strip_html(content)
    solution_text = _strip_html(solution)
    option_texts = [_strip_html(opt) for opt in options]
    kp_names = [kp.get('name', '') for kp in keypoints] if keypoints else []

    # 构造用户消息
    user_message = f"""请诊断以下错题的错误原因：

【题目】{content_text}

【选项】
{chr(10).join(f"{chr(65+i)}. {opt}" for i, opt in enumerate(option_texts))}

【我的答案】{_idx_to_label(your_answer)}
【正确答案】{_idx_to_label(correct_answer)}
【知识点】{', '.join(kp_names) if kp_names else '未知'}
【用时】{f'{time_spent_sec:.1f}秒' if time_spent_sec else '未知'}"""

    if solution_text:
        user_message += f"\n\n【官方解析】{solution_text}"

    # 截断过长的消息（保留前 3000 字符）
    if len(user_message) > 3000:
        user_message = user_message[:3000] + "\n...(内容已截断)"

    system_prompt = _load_diagnosis_skill()

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')
    client = _get_client()

    last_error = None
    for attempt in range(retry):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)

            # 验证必需字段
            if 'confidence' not in result:
                raise ValueError("LLM 返回缺少必需字段")

            result.setdefault('explanation', '')
            result.setdefault('countermeasure', '')
            result.setdefault('specific_error', '')
            return result

        except Exception as e:
            last_error = e
            if attempt < retry - 1:
                time.sleep(2 ** attempt)
            continue

    # 所有重试都失败，返回默认值
    return {
        "confidence": 0.0,
        "explanation": f"LLM 调用失败（{str(last_error)}），请人工判断",
        "specific_error": "",
        "countermeasure": "",
    }


def diagnose_guess(
    content: str,
    options: list,
    your_answer: str,
    correct_answer: str,
    solution: str,
    keypoints: list,
    time_spent_sec: Optional[float],
) -> dict:
    """调用 LLM 辅助判断是否蒙对。

    Args:
        同 diagnose_error

    Returns:
        dict: {"is_guessed": bool, "confidence": float, "reason": str}
    """
    content_text = _strip_html(content)
    solution_text = _strip_html(solution)
    option_texts = [_strip_html(opt) for opt in options]

    user_message = f"""请判断以下答对的题目是否为"蒙对"（碰运气猜对）：

【题目】{content_text[:500]}

【选项】
{chr(10).join(f"{chr(65+i)}. {opt[:100]}" for i, opt in enumerate(option_texts))}

【考生答案】{_idx_to_label(your_answer)}
【正确答案】{_idx_to_label(correct_answer)}（两者相同，考生答对）
【用时】{f'{time_spent_sec:.1f}秒' if time_spent_sec else '未知'}"""

    if solution_text:
        user_message += f"\n\n【解析摘要】{solution_text[:300]}"

    system_prompt = """你是一位公考辅导专家。请判断考生是否"蒙对"了这道题。
蒙对的特征：用时极短（<10秒）、考生答案与题目选项间无明显推理关联、题目难度高但做对。
请输出 JSON：{"is_guessed": true/false, "confidence": 0.0~1.0, "reason": "判断理由"}"""

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content.strip())
        return {
            "is_guessed": result.get("is_guessed", False),
            "confidence": result.get("confidence", 0.5),
            "reason": result.get("reason", ""),
        }
    except Exception:
        return {"is_guessed": False, "confidence": 0.0, "reason": "LLM 调用失败"}


def diagnose_difficulty(
    content: str,
    solution: str,
    keypoints: list,
) -> dict:
    """当 global_correct_ratio 为空时，使用 LLM 评估题目难度。

    Returns:
        dict: {"difficulty": "easy/medium/hard", "confidence": float}
    """
    content_text = _strip_html(content)
    solution_text = _strip_html(solution)

    user_message = f"""请评估以下题目的难度等级：

【题目】{content_text[:500]}
【解析】{solution_text[:500] if solution_text else '无'}
【知识点】{', '.join(kp.get('name', '') for kp in keypoints) if keypoints else '未知'}"""

    system_prompt = """你是公考命题专家。请根据题目复杂度、知识点难度、解析长度评估难度。
输出 JSON：{"difficulty": "easy/medium/hard", "confidence": 0.0~1.0}"""

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content.strip())
        diff = result.get("difficulty", "medium")
        if diff not in ("easy", "medium", "hard"):
            diff = "medium"
        return {"difficulty": diff, "confidence": result.get("confidence", 0.5)}
    except Exception:
        return {"difficulty": "medium", "confidence": 0.0}


def chat_with_context(
    user_query: str,
    db_context: str,
    conversation_history: list = None,
) -> str:
    """带知识库上下文的对话。

    Args:
        user_query: 用户问题
        db_context: 从数据库提取的统计信息文本
        conversation_history: 历史消息列表 [{"role": "user/assistant", "content": "..."}]

    Returns:
        str: AI 回复
    """
    import datetime as _dt
    today = _dt.date.today().isoformat()
    system_prompt = f"""你是一位专业的公考备考顾问。今天是 {today}。

拥有以下考生的学习数据：
{db_context}

请基于以上数据回答考生的问题。你的建议应该：
1. 数据驱动：引用具体数字和趋势
2. 聚焦模块层面分析，禁止罗列具体知识点名称（如"前后呼应""混搭填空"等）和错误类型标签（如"概念混淆""计算失误"等）
3. 可操作：给出具体的学习建议和计划
4. 鼓励性：保持积极正面的语气

回复格式要求：使用 Markdown 格式组织内容，适当使用标题、列表、加粗等增强可读性。"""


    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history[-10:])  # 保留最近10轮对话
    messages.append({"role": "user", "content": user_query})

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except ValueError:
        # API Key 未配置
        return "抱歉，AI 服务未配置。请在 config.yaml 中设置 llm.api_key，或设置环境变量 DEEPSEEK_API_KEY。"
    except Exception as e:
        return f"抱歉，AI 服务暂时不可用：{str(e)}"


def _strip_html(html_text: str) -> str:
    """去除 HTML 标签，保留纯文本。"""
    if not html_text:
        return ""
    # 移除 <br> 和 <br/> 替换为换行
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    # 移除其他 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 处理 HTML 实体
    text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&amp;', '&').replace('&quot;', '"')
    # 压缩多余空白
    text = re.sub(r'\n\s*\n', '\n', text)
    text = text.strip()
    return text


def _idx_to_label(idx: str) -> str:
    """将答案索引转换为 A/B/C/D 标签。"""
    mapping = {'0': 'A', '1': 'B', '2': 'C', '3': 'D',
               'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'}
    return mapping.get(str(idx), str(idx))


def diagnose_error_batch(
    questions: list[dict],
    retry: int = 2,
    user_profile: str = '',
) -> list[dict]:
    """批量诊断多道错题（8 道一批，大幅节省 token）。

    将最多 8 道题打包为一个 API 调用，共享 system prompt，
    相比逐题调用降低约 80% 成本。

    Args:
        questions: 题目列表，每项含 content, options, your_answer,
                   correct_answer, solution, keypoints, time_spent_sec,
                   global_correct_ratio, 可选 module
        retry: 重试次数
        user_profile: 用户能力画像文本，用于个性化诊断

    Returns:
        list[dict]: 与输入同序的诊断结果
    """
    if not questions:
        return []

    # 构建紧凑的批量消息（含难度信息 + 选项全文）
    items = []
    for i, q in enumerate(questions):
        content = _strip_html(q.get('content', ''))[:300]
        raw_opts = q.get('options', [])
        opts = [_strip_html(o)[:80] for o in raw_opts]
        sol = _strip_html(q.get('solution', ''))[:300]
        kps = [k.get('name', '') for k in q.get('keypoints', [])]
        label_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D'}
        mod = q.get('module', '')
        mod_hint = f"模块={mod}，" if mod else ''

        # 考生选错的选项
        your_idx = str(q.get('your_answer', ''))
        your_label = label_map.get(your_idx, '?')
        your_opt_text = opts[int(your_idx)] if your_idx.isdigit() and int(your_idx) < len(opts) else ''
        correct_idx = str(q.get('correct_answer', ''))
        correct_label = label_map.get(correct_idx, '?')
        correct_opt_text = opts[int(correct_idx)] if correct_idx.isdigit() and int(correct_idx) < len(opts) else ''

        # 难度标记
        gcr = q.get('global_correct_ratio')
        diff_hint = ''
        if gcr is not None:
            try:
                gcr_val = float(gcr)
                if gcr_val < 20:
                    diff_hint = f' [全站正确率仅{gcr_val:.0f}%，极难题]'
                elif gcr_val < 40:
                    diff_hint = f' [全站正确率{gcr_val:.0f}%，偏难题]'
                elif gcr_val >= 80:
                    diff_hint = f' [全站正确率{gcr_val:.0f}%，简单题不应错]'
            except (ValueError, TypeError):
                pass

        item = (
            f"题{i+1}：{mod_hint}{content}{diff_hint}\n"
            f"选项：{' | '.join(f'{chr(65+j)}.{o}' for j, o in enumerate(opts))}\n"
            f"考生选了{your_label}：\"{your_opt_text}\" | 正确答案{correct_label}：\"{correct_opt_text}\"\n"
            f"知识点：{','.join(kps[:3])} | 用时：{q.get('time_spent_sec','?')}秒"
        )
        if sol:
            item += f"\n解析：{sol}"
        items.append(item)

    batch_text = '\n\n---\n\n'.join(items)
    user_message = (
        f"诊断以下 {len(questions)} 道行测错题的错误原因。"
        f"输出 JSON，每道题 specific_error（一句话说清错在哪）、countermeasure（一句可执行的对策/技巧，告诉考生下次怎么避免，20-60字）、"
        f"explanation（为什么错，20-60字）、confidence（0~1）：\n\n{batch_text}"
    )

    profile_section = ''
    if user_profile:
        profile_section = (
            f"\n\n【考生能力画像】\n{user_profile}\n"
            f"请结合画像进行个性化诊断：如果某错题符合画像中的薄弱模式，请在explanation中指出；"
            f"如果是新出现的错误，请指出需要关注。"
        )

    system_prompt = (
        "你是公考行测辅导专家。对每道错题进行深度诊断。\n\n"
        "【诊断方法】先推理后判断：\n"
        "1. 先看正确答案的选项内容，理解正确解法应该是什么\n"
        "2. 再看考生选错的选项内容，分析选了它说明考生走了哪条错误路径\n"
        "3. 结合用时和全站正确率，判断错误的根本原因\n\n"
        "【常见错误路径对照】\n"
        "- 选错选项与正确选项含义相反 → 审题时忽略了否定词/提问方向\n"
        "- 选错选项是某个中间计算结果 → 公式步骤不完整，差最后一步\n"
        "- 选错选项与正确选项是同类但不同对象 → 概念区分不清（如环比vs同比）\n"
        "- 选错选项是题干中出现的数字 → 直接抄数，没做任何计算\n"
        "- 用时极短（<10秒）+全站正确率高 → 可能是蒙的或根本没读题\n"
        "- 用时正常但选了明显不相关的选项 → 知识点完全不会，凭感觉猜\n\n"
        "对每道题输出以下字段：\n"
        "- specific_error：一句话说清错在哪个步骤（必须结合考生具体选错的选项内容来分析，不要泛泛说\"审题不清\"，要说清楚审题时漏掉了哪个词/哪个条件）\n"
        "- countermeasure：针对这个错误的一句可执行对策（20-60字）\n"
        "- explanation：简述考生可能的思维路径（如\"选了B说明他把增长量当成了增长率\"），20-60字\n"
        "- confidence：0-1 置信度（诊断依据充分→高；信息不足→低）\n\n"
        "置信度校准：如果考生的错误路径有多种可能，降低 confidence。如果错选选项与正确选项内容差异明显、容易推断错误路径，可以提高 confidence。\n"
        + profile_section + "\n"
        '输出 JSON：{"items":[{"specific_error":"把环比当成同比——题干给的是上月数据应套环比公式，但选了同比增长率","countermeasure":"先圈出题干时间词确认比较基准——和上月比用环比，和去年同月比用同比","explanation":"看到增长率就直接套了同比公式，没检查比较基准是上月还是去年同月","confidence":0.85},...]}'
    )

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')

    last_err = ''
    for attempt in range(retry + 1):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content.strip()
            data = json.loads(text)

            # 兼容 {items: [...]} 和裸数组两种格式
            if isinstance(data, dict):
                results = data.get('items', data.get('results', list(data.values())))
            elif isinstance(data, list):
                results = data
            else:
                raise ValueError(f"意外格式: {type(data)}")

            # 补齐缺失字段
            out = []
            for r in results:
                if not isinstance(r, dict):
                    r = {}
                out.append({
                    'confidence': float(r.get('confidence', 0.3)),
                    'explanation': str(r.get('explanation', ''))[:120],
                    'specific_error': str(r.get('specific_error', ''))[:80],
                    'countermeasure': str(r.get('countermeasure', ''))[:80],
                })

            # 补齐到输入长度
            while len(out) < len(questions):
                out.append({'confidence': 0.0, 'explanation': '', 'specific_error': '', 'countermeasure': ''})
            return out[:len(questions)]

        except Exception as e:
            last_err = f'{type(e).__name__}: {e}'
            if attempt < retry:
                time.sleep(2 ** attempt)
            continue

    # 全部失败：返回兜底（带上真实错误信息）
    return [{'confidence': 0.0, 'explanation': f'诊断失败({last_err[:60]})', 'specific_error': '', 'countermeasure': ''} for _ in questions]


def evaluate_shenlun_answer(
    question: str = '',
    materials: str = '',
    answer: str = '',
    question_type: str = '',
    word_limit: str = '',
    score: str = '',
) -> dict:
    """AI 批改申论答案。

    Returns:
        dict: {total_score, content_score, structure_score, language_score, comments, improvement}
    """
    system_prompt = (
        "你是公考申论阅卷专家。请按评分标准批改答案。"
        "申论评分维度：内容要点（是否覆盖核心得分点）、结构逻辑（层次清晰/论证有力）、"
        "语言表达（规范/简洁/无口语）。满分100。"
        "输出 JSON：{\"total_score\":75,\"content_score\":30,\"structure_score\":25,"
        "\"language_score\":20,\"comments\":\"逐段点评\",\"improvement\":\"改进建议\"}"
    )

    mat_text = f"\n【给定资料】\n{materials}" if materials else ""
    user_msg = (
        f"题型：{question_type}，分值：{score}分，字数：{word_limit}\n"
        f"【题目】{question}\n{mat_text}\n【考生答案】\n{answer}\n"
        f"请批改。输出JSON。"
    )

    llm_config = _load_llm_config()
    client = _get_client()

    try:
        r = client.chat.completions.create(
            model=llm_config.get('model', 'deepseek-chat'),
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_msg},
            ],
            max_tokens=600, temperature=0.3,
            response_format={'type': 'json_object'},
        )
        result = json.loads(r.choices[0].message.content)
        return {
            'total_score': int(result.get('total_score', 70)),
            'content_score': int(result.get('content_score', 25)),
            'structure_score': int(result.get('structure_score', 25)),
            'language_score': int(result.get('language_score', 20)),
            'comments': result.get('comments', ''),
            'improvement': result.get('improvement', ''),
        }
    except Exception as e:
        return {
            'total_score': 0, 'content_score': 0, 'structure_score': 0, 'language_score': 0,
            'comments': f'批改失败：{e}', 'improvement': '',
        }


