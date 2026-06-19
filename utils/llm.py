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
- error_type: 错误类型，必须是以下之一：计算失误、公式用错、概念混淆、审题不清、时间不足蒙的、记忆盲区、放弃、其他
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
        dict: {"error_type": str, "confidence": float, "explanation": str}
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
            if 'error_type' not in result or 'confidence' not in result:
                raise ValueError("LLM 返回缺少必需字段")

            # 标准化 error_type
            result['error_type'] = _normalize_error_type(result['error_type'])
            result.setdefault('explanation', '')
            return result

        except Exception as e:
            last_error = e
            if attempt < retry - 1:
                time.sleep(2 ** attempt)
            continue

    # 所有重试都失败，返回默认值
    return {
        "error_type": "其他",
        "confidence": 0.0,
        "explanation": f"LLM 调用失败（{str(last_error)}），请人工判断",
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
2. 个性化：针对考生的薄弱环节
3. 可操作：给出具体的学习建议和计划
4. 鼓励性：保持积极正面的语气"""


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
) -> list[dict]:
    """批量诊断多道错题（5 道一批，大幅节省 token）。

    将最多 5 道题打包为一个 API 调用，共享 system prompt，
    相比逐题调用降低约 80% 成本。

    Args:
        questions: 题目列表，每项含 content, options, your_answer,
                   correct_answer, solution, keypoints, time_spent_sec,
                   可选 module（模块名，用于加权诊断）
        retry: 重试次数

    Returns:
        list[dict]: 与输入同序的诊断结果
    """
    if not questions:
        return []

    # 模块→默认错因 映射
    MODULE_DEFAULT = {
        '常识判断': '记忆盲区', '政治理论': '记忆盲区',
        '资料分析': '计算失误', '数量关系': '公式用错',
        '言语理解与表达': '审题不清', '判断推理': '概念混淆',
    }

    # 构建紧凑的批量消息
    items = []
    for i, q in enumerate(questions):
        content = _strip_html(q.get('content', ''))[:250]
        opts = [_strip_html(o)[:50] for o in q.get('options', [])]
        sol = _strip_html(q.get('solution', ''))[:150]
        kps = [k.get('name', '') for k in q.get('keypoints', [])]
        label_map = {'0': 'A', '1': 'B', '2': 'C', '3': 'D'}
        mod = q.get('module', '')
        mod_hint = f"模块={mod}，" if mod else ''

        item = (
            f"题{i+1}：{mod_hint}{content}\n"
            f"选项：{' | '.join(f'{chr(65+j)}.{o}' for j, o in enumerate(opts))}\n"
            f"答：{label_map.get(str(q.get('your_answer','')), '?')} "
            f"正解：{label_map.get(str(q.get('correct_answer','')), '?')} "
            f"知识点：{','.join(kps[:3])} "
            f"用时：{q.get('time_spent_sec','?')}秒"
        )
        if sol:
            item += f"\n解析摘要：{sol}"
        items.append(item)

    batch_text = '\n\n---\n\n'.join(items)
    user_message = (
        f"诊断以下 {len(questions)} 道行测错题的错误原因。"
        f"输出 JSON，每道题 error_type（计算失误/公式用错/概念混淆/审题不清/时间不足蒙的/记忆盲区/放弃）、"
        f"confidence（0~1）和 explanation（≤40字）：\n\n{batch_text}"
    )

    system_prompt = (
        "你是公考行测辅导专家。请深度诊断每道错题的错误原因。\n"
        "对每道题输出：\n"
        "1. error_type：从「计算失误/公式用错/概念混淆/审题不清/时间不足蒙的/记忆盲区/放弃」中选一个最匹配的\n"
        "2. specific_error：一句话具体描述错在哪（如\"混淆了环比与同比的定义\"，而非笼统的\"概念混淆\"）\n"
        "3. explanation：详细分析——\"你选X可能是因为...但正确答案Y的原因是...两者区别在于...\"（40-100字）\n"
        "4. confidence：0-1置信度\n\n"
        "模块默认判断规则：\n"
        "- 常识判断/政治理论：优先「记忆盲区」\n"
        "- 资料分析：优先「计算失误」或「公式用错」\n"
        "- 数量关系：优先「公式用错」或「计算失误」\n"
        "- 言语理解与表达：优先「审题不清」或「概念混淆」\n"
        "- 判断推理：优先「概念混淆」或「审题不清」\n"
        "用时<10秒且无推理→「时间不足蒙的」\n\n"
        "诊断要具体可操作——看完分析后考生能明白自己为什么错、下次怎么避免。\n"
        '输出 JSON：{"items":[{"error_type":"概念混淆","specific_error":"混淆了环比与同比","explanation":"你选A可能是因为看到增长率就按同比算了，但题目给的是上月数据，应该用环比。同比是和去年同期比，环比是和上个月比。","confidence":0.85},...]}'
    )

    llm_config = _load_llm_config()
    model = llm_config.get('model', 'deepseek-chat')

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
                    'error_type': _normalize_error_type(r.get('error_type', '其他')),
                    'confidence': float(r.get('confidence', 0.3)),
                    'explanation': str(r.get('explanation', ''))[:120],
                })

            # 补齐到输入长度
            while len(out) < len(questions):
                out.append({'error_type': '其他', 'confidence': 0.0, 'explanation': ''})
            return out[:len(questions)]

        except Exception:
            if attempt < retry:
                time.sleep(2 ** attempt)
            continue

    # 全部失败：返回兜底
    return [{'error_type': '其他', 'confidence': 0.0, 'explanation': '诊断失败'} for _ in questions]


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


def _normalize_error_type(error_type: str) -> str:
    """标准化错误类型标签，支持 LLM 常见变体。"""
    alias_map = {
        '知识点错误': '记忆盲区', '知识点不熟': '记忆盲区', '知识盲区': '记忆盲区',
        '遗忘': '记忆盲区', '没见过': '记忆盲区', '没掌握': '记忆盲区',
        '粗心': '审题不清', '看错': '审题不清', '马虎': '审题不清',
        '没看清': '审题不清', '误解': '审题不清', '理解错误': '概念混淆',
        '算错': '计算失误', '计算错误': '计算失误',
        '用错公式': '公式用错', '记错公式': '公式用错',
        '蒙': '时间不足蒙的', '猜': '时间不足蒙的', '没时间': '时间不足蒙的',
        '来不及': '时间不足蒙的', '不会': '放弃',
    }
    et = error_type.strip()
    if et in alias_map:
        return alias_map[et]
    valid = ['计算失误', '公式用错', '概念混淆', '审题不清',
             '时间不足蒙的', '记忆盲区', '放弃', '其他']
    for vt in valid:
        if vt in et:
            return vt
    return '其他'
