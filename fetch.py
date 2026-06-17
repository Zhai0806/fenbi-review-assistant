"""粉笔模考数据抓取脚本

从粉笔网页版抓取并合并做题数据，生成结构化的 merged_report.json。

用法:
    python fetch.py --exam-key 1_1_3jslr2e
    python fetch.py --url "https://spa.fenbi.com/..."

功能流程:
    1. 从 config.yaml 读取 cookie 和通用请求头
    2. 通过命令行参数获取 EXAM_KEY
    3. 自动请求 getSolution 接口，提取长 key（SOLUTION_KEY）
    4. 并发请求四个接口：getSolution、static/solution、getMeta、getMark
    5. 合并数据生成 merged_report.json 并保存到 data/reports/
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import requests
import yaml


def load_config() -> dict:
    """加载 config.yaml 配置文件。"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在：{config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def build_headers(config: dict) -> dict:
    """构建请求头。"""
    fenbi = config.get('fenbi', {})
    headers = fenbi.get('headers', {}).copy()
    headers['cookie'] = fenbi.get('cookie', '')
    return headers


def build_params(config: dict, extra: dict = None, routecs: str = '') -> dict:
    """构建查询参数（routecs, kav, av, hav 等粉笔通用参数）。

    Args:
        config: 配置字典
        extra: 额外的查询参数（如 key, requestKey, exerciseKey, type, format 等）
        routecs: 覆盖 config 中的 routecs（从 URL 提取）

    Returns:
        dict: 合并后的查询参数字典
    """
    fenbi = config.get('fenbi', {})
    params = {
        'routecs': routecs or fenbi.get('routecs', 'xingce'),
        'kav': fenbi.get('kav', 125),
        'av': fenbi.get('av', 127),
        'hav': fenbi.get('hav', 125),
        'app': fenbi.get('app', 'web'),
        'apcid': fenbi.get('apcid', 0),
        'deviceId': fenbi.get('deviceId', ''),
        'gav': fenbi.get('gav', 2),
    }
    if extra:
        params.update(extra)
    return params


def extract_exam_key_from_url(url: str) -> tuple[str, str]:
    """从完整报告页面 URL 中提取短 key 和 routecs。

    支持的 URL 格式：
    - https://spa.fenbi.com/.../solution/1_1_3jslr2e?routecs=xingce
    - https://spa.fenbi.com/.../solution/1_123_2g4cco5?routecs=szyfzc

    Returns:
        tuple[str, str]: (exam_key, routecs)，routecs 默认 'xingce'
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    routecs = qs.get('routecs', [None])[0] or 'xingce'

    exam_key = qs.get('examKey', [None])[0]
    if exam_key:
        return exam_key, routecs

    match = re.search(r'([\w]+_[\w]+_[\w]+)', url)
    if match:
        return match.group(1), routecs

    print("❌ 无法从 URL 中提取 examKey，请使用 --exam-key 直接指定")
    sys.exit(1)


def fetch_exam_date(config: dict, exam_key: str, routecs: str = '') -> str:
    """从粉笔练习历史 API 获取真实的考试/练习日期。

    Args:
        config: 配置字典
        exam_key: 短 key（如 1_1_3jslr2e）

    Returns:
        str: YYYY-MM-DD 格式的日期，获取失败返回空字符串
    """
    fenbi = config.get('fenbi', {})
    api_base = fenbi.get('api_base', 'https://tiku.fenbi.com/combine')
    headers = build_headers(config)

    url = f"{api_base}/exercise/getExerciseBriefHistory"
    extra = {
        'limit': '50',
        'noCacheTag': str(int(time.time())),
        'cursor': '',
    }
    # categoryId=1 只对行测有效；其他考试不传此参数避免空结果
    if routecs in ('xingce', '') and config.get('fenbi', {}).get('routecs', 'xingce') in ('xingce', ''):
        extra['categoryId'] = '1'
    params = build_params(config, extra=extra, routecs=routecs)

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return ''

    resp_data = data.get('data') or {}
    items = resp_data.get('historyItems', [])
    for item in items:
        if item.get('exerciseKey') == exam_key:
            ts_ms = item.get('updatedTime', 0)
            if ts_ms:
                dt = datetime.fromtimestamp(ts_ms / 1000.0)
                return dt.strftime('%Y-%m-%d')
            break

    return ''


def fetch_api(url: str, headers: dict, params: dict = None,
              method: str = 'GET', json_data: dict = None,
              retry: int = 3) -> dict:
    """带重试的 API 请求。

    Args:
        url: 请求 URL
        headers: 请求头
        params: 查询参数
        method: HTTP 方法
        json_data: JSON 请求体（POST 时使用）
        retry: 重试次数

    Returns:
        dict: JSON 响应
    """
    for attempt in range(retry):
        try:
            if method.upper() == 'POST':
                resp = requests.post(
                    url, headers=headers, params=params,
                    json=json_data, timeout=30
                )
            else:
                resp = requests.get(
                    url, headers=headers, params=params, timeout=30
                )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < retry - 1:
                wait = 2 ** attempt
                print(f"⚠️ 请求失败，{wait}秒后重试（{attempt+1}/{retry}）：{e}")
                time.sleep(wait)
            else:
                print(f"❌ 请求最终失败：{e}")
                return None


def _extract_user_answers(html_text: str) -> dict:
    """从 getSolution HTML 中提取用户答题数据。

    HTML 中内嵌了 "userAnswers" JSON 对象，结构为：
    {
        "3_1_gtv1m": {
            "key": "3_1_gtv1m",
            "time": 45,              // 做题用时（秒）
            "answer": {"choice": "1", "type": 201},  // 用户选择的答案
            "status": 1,             // 1=正确, -1=错误, 0=未作答
            "scoreRate": 1.0,        // 得分率
        },
        ...
    }

    Args:
        html_text: getSolution 接口返回的 HTML 文本

    Returns:
        dict: 以 globalId 为 key 的用户答题数据字典；提取失败返回 {}
    """
    # 找到 "userAnswers" 的起始位置
    idx = html_text.find('"userAnswers"')
    if idx < 0:
        return {}

    # 找到冒号后的第一个 {
    brace_start = html_text.find('{', idx)
    if brace_start < 0:
        return {}

    # 括号匹配，提取完整 JSON 对象
    depth = 0
    for i in range(brace_start, min(brace_start + 500000, len(html_text))):
        if html_text[i] == '{':
            depth += 1
        elif html_text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    user_answers = json.loads(html_text[brace_start:i + 1])
                    return user_answers if isinstance(user_answers, dict) else {}
                except json.JSONDecodeError:
                    return {}

    return {}


def get_solution_key(config: dict, exam_key: str, routecs: str = '') -> tuple[str, dict]:
    """通过 getSolution 接口获取长 key 和用户答题数据。

    请求 getSolution 接口（format=html），从返回的 HTML 中提取：
    - requestKey：用于后续 API 请求的长 key
    - userAnswers：用户的答题记录（答案、用时、得分等）

    Args:
        config: 配置字典
        exam_key: 短 key（如 1_1_3jslr2e）
        routecs: 考试类型路由（如 xingce / szyfzc），从 URL 提取

    Returns:
        tuple[str, dict]: (长 key SOLUTION_KEY, 用户答题数据字典)
    """
    fenbi = config.get('fenbi', {})
    api_base = fenbi.get('api_base', 'https://tiku.fenbi.com/combine')
    headers = build_headers(config)
    params = build_params(config, extra={
        'key': exam_key,
        'format': 'html',
    }, routecs=routecs)

    url = f"{api_base}/exercise/getSolution"

    print(f"📡 请求 getSolution 获取长 key 和用户答题数据...")
    print(f"   URL: {url}")

    # format=html 返回 HTML，不能直接 resp.json()，需要 resp.text
    html_text = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            html_text = resp.text
            break
        except requests.exceptions.RequestException as e:
            if attempt < 2:
                wait = 2 ** attempt
                print(f"⚠️ 请求失败，{wait}秒后重试（{attempt+1}/3）：{e}")
                time.sleep(wait)
            else:
                print(f"❌ 请求最终失败：{e}")
                print("❌ 获取长 key 失败，请检查 cookie 是否过期")
                sys.exit(1)

    if not html_text:
        print("❌ 获取长 key 失败，请检查 cookie 是否过期")
        sys.exit(1)

    # 从 HTML 中提取用户答题数据
    user_answers = _extract_user_answers(html_text)
    if user_answers:
        print(f"   ✅ 提取到 {len(user_answers)} 条用户答题记录")
    else:
        print("   ⚠️ 未提取到用户答题数据（可能未作答此试卷）")

    # 从 HTML 中提取 requestKey
    # 模式1: "requestKey":"VALUE" (JSON 嵌入)
    match = re.search(r'"requestKey"\s*:\s*"([A-Za-z0-9_\-]+)"', html_text)
    if match:
        solution_key = match.group(1)
        print(f"✅ 获取到长 key：{solution_key}")
        return solution_key, user_answers

    # 模式2: 'requestKey':'VALUE'
    match = re.search(r"'requestKey'\s*:\s*'([A-Za-z0-9_\-]+)'", html_text)
    if match:
        solution_key = match.group(1)
        print(f"✅ 获取到长 key：{solution_key}")
        return solution_key, user_answers

    # 模式3: requestKey = "VALUE" 或 requestKey="VALUE"
    match = re.search(r'requestKey\s*=\s*["\']([A-Za-z0-9_\-]+)["\']', html_text)
    if match:
        solution_key = match.group(1)
        print(f"✅ 获取到长 key：{solution_key}")
        return solution_key, user_answers

    # 模式4: 尝试在可能的关键词附近查找长 key（超长 base64-like 字符串）
    match = re.search(r'requestKey["\'\s]*[:=]["\'\s]*([A-Za-z0-9_\-]{100,})', html_text)
    if match:
        solution_key = match.group(1)
        print(f"✅ 获取到长 key：{solution_key}")
        return solution_key, user_answers

    print(f"❌ 无法从 HTML 中提取 requestKey。响应前 500 字符：")
    print(html_text[:500])
    sys.exit(1)


def fetch_all_data(config: dict, exam_key: str, solution_key: str, routecs: str = '') -> dict:
    """并发请求四个接口获取全部数据。

    Args:
        config: 配置字典
        exam_key: 短 key
        solution_key: 长 key

    Returns:
        dict: 包含四个接口返回数据的字典
    """
    fenbi = config.get('fenbi', {})
    api_base = fenbi.get('api_base', 'https://tiku.fenbi.com/combine')
    headers = build_headers(config)

    tasks = {}

    # 接口1：static/solution（静态做题数据，主数据源）
    url1 = f"{api_base}/static/solution"
    tasks['static_solution'] = {
        'url': url1,
        'headers': headers,
        'params': build_params(config, extra={
            'key': solution_key,
            'type': str(fenbi.get('solution_type', 1)),
        }, routecs=routecs),
        'method': 'GET',
    }

    # 接口2：getMeta（全站正确率等元数据，使用长 key）
    url2 = f"{api_base}/question/getMeta"
    tasks['meta'] = {
        'url': url2,
        'headers': headers,
        'params': build_params(config, extra={'requestKey': solution_key}, routecs=routecs),
        'method': 'GET',
    }

    # 接口3：getMark（用户标记/收藏数据）
    url3 = f"{api_base}/mark/getMark"
    tasks['mark'] = {
        'url': url3,
        'headers': headers,
        'params': build_params(config, extra={'exerciseKey': exam_key}, routecs=routecs),
        'method': 'GET',
    }

    results = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        for name, task in tasks.items():
            fut = executor.submit(
                fetch_api,
                task['url'], task['headers'], task['params'],
                task['method']
            )
            futures[fut] = name

        for fut in as_completed(futures):
            name = futures[fut]
            try:
                results[name] = fut.result()
                status = "✅" if results[name] else "❌"
                print(f"  {status} {name}")
            except Exception as e:
                print(f"  ❌ {name}：{e}")
                results[name] = None

    return results


def normalize_answer_index(answer) -> str:
    """将答案标准化为索引字符串。

    粉笔的答案可能是 "0"（数字字符串）、0（数字）、"A"（字母）等格式。
    统一转换为 "0"/"1"/"2"/"3" 格式。
    """
    if answer is None:
        return ""
    s = str(answer).strip().upper()
    # 字母 → 数字
    letter_map = {'A': '0', 'B': '1', 'C': '2', 'D': '3',
                  '0': '0', '1': '1', '2': '2', '3': '3'}
    return letter_map.get(s, s)


def merge_data(api_results: dict, user_answers: dict = None) -> list[dict]:
    """合并所有数据，生成完整的题目列表。

    合并逻辑：
    - 以 static/solution 的 solutions 列表为主骨架
    - 从 getSolution HTML 的 userAnswers 补充用户答题数据
    - 从 getMeta 补充 global_correct_ratio、global_total_count
    - 从 getMark 补充 user_marked

    Args:
        api_results: fetch_all_data 的返回结果
        user_answers: getSolution HTML 中提取的用户答题数据
                     格式：{globalId: {key, time, answer, status, scoreRate}}

    Returns:
        tuple[list[dict], list[dict]]: (合并后的题目列表, 材料列表)
    """
    if user_answers is None:
        user_answers = {}

    # 提取核心数据
    static_data = api_results.get('static_solution', {}) or {}
    materials = static_data.get('materials', []) if isinstance(static_data, dict) else []
    meta_data = api_results.get('meta', {}) or {}
    mark_data = api_results.get('mark', {}) or {}

    # 获取题目列表
    exercises = _extract_exercises(static_data)

    # 构建 meta 索引（meta 返回 {code, data: {globalId: {...}}, msg}）
    meta_index = {}
    if isinstance(meta_data, dict):
        meta_raw = meta_data.get('data', meta_data)
        if isinstance(meta_raw, dict):
            meta_index = meta_raw

    # 用户标记题目的 key 集合
    marked_keys = set()
    if isinstance(mark_data, dict):
        marked_list = mark_data.get('data', mark_data.get('list', []))
        if isinstance(marked_list, list):
            for item in marked_list:
                if isinstance(item, dict):
                    marked_keys.add(str(item.get('exerciseId', item.get('key', ''))))
                elif isinstance(item, str):
                    marked_keys.add(item)

    merged = []
    for ex in exercises:
        # 使用 globalId（新 API 格式如 "3_1_gtv1m"）作为主键
        eid = str(ex.get('globalId', ex.get('exerciseId', ex.get('id', ex.get('key', '')))))

        # 从 meta 补充
        meta_info = meta_index.get(eid, {})
        if not isinstance(meta_info, dict):
            meta_info = {}

        # 从 user_answers 获取用户答题数据
        ua = user_answers.get(eid, {})
        if not isinstance(ua, dict):
            ua = {}

        # 提取 options（新 API 嵌套在 accessories[0]['options']）
        options = _extract_options(ex)

        # 提取 correctAnswer（新 API 为 {"choice": "3", "type": 201}）
        correct_answer = _extract_correct_answer(ex)

        # 提取用户答案（userAnswers.answer 格式：{"choice": "1", "type": 201}）
        user_answer_raw = ua.get('answer', '')
        if isinstance(user_answer_raw, dict):
            user_answer_raw = str(user_answer_raw.get('choice', ''))
        your_answer = normalize_answer_index(user_answer_raw)

        question = {
            'key': eid,
            'id': ex.get('id', ex.get('exerciseId', '')),
            'content': ex.get('content', ''),
            'options': options,
            'correct_answer': normalize_answer_index(correct_answer),
            'solution': ex.get('solution', ''),
            'keypoints': ex.get('keypoints', ex.get('keyPoints', [])),
            'source': ex.get('source', ''),
            'your_answer': your_answer,
            'time_spent_sec': ua.get('time'),
            'status': ua.get('status', 0),
            'score_rate': ua.get('scoreRate', 0),
            'global_correct_ratio': meta_info.get('correctRatio',
                                        meta_info.get('global_correct_ratio')),
            'global_total_count': meta_info.get('totalCount',
                                        meta_info.get('global_total_count')),
            'user_marked': eid in marked_keys,
        }

        # 类型转换
        try:
            question['status'] = int(question['status'])
        except (ValueError, TypeError):
            question['status'] = 0

        try:
            question['score_rate'] = float(question['score_rate'])
        except (ValueError, TypeError):
            question['score_rate'] = 0.0

        if question['time_spent_sec'] is not None:
            try:
                question['time_spent_sec'] = float(question['time_spent_sec'])
            except (ValueError, TypeError):
                question['time_spent_sec'] = None

        if question.get('global_correct_ratio') is not None:
            try:
                question['global_correct_ratio'] = float(question['global_correct_ratio'])
            except (ValueError, TypeError):
                question['global_correct_ratio'] = None

        # 保留材料引用（资料分析题共用材料用）
        material_keys = ex.get('materialKeys', [])
        if material_keys:
            question['materialKeys'] = material_keys

        merged.append(question)

    return merged, materials


def _extract_options(ex: dict) -> list:
    """从题目数据中提取选项列表。

    支持格式：
    - ex.options: ['A. xxx', 'B. xxx']（旧格式）
    - ex.accessories[0].options: ['A. xxx', 'B. xxx']（新格式）
    """
    # 直接 options 字段
    opts = ex.get('options')
    if isinstance(opts, list) and len(opts) > 0:
        return opts

    # 嵌套在 accessories 中
    accessories = ex.get('accessories', [])
    if isinstance(accessories, list) and len(accessories) > 0:
        for acc in accessories:
            if isinstance(acc, dict):
                opts = acc.get('options')
                if isinstance(opts, list) and len(opts) > 0:
                    return opts

    return []


def _extract_correct_answer(ex: dict) -> str:
    """从题目数据中提取正确答案。

    支持格式：
    - ex.correctAnswer: '0' / 'A'（旧格式，字符串）
    - ex.correctAnswer: {'choice': '3', 'type': 201}（新格式，对象）
    - ex.answer: '0'
    """
    answer = ex.get('correctAnswer', ex.get('answer', ''))

    if isinstance(answer, dict):
        # 新格式：{"choice": "3"} → 粉笔 choice = 选项索引（0/1/2/3）
        return str(answer.get('choice', ''))

    return str(answer)


def _extract_exercises(data: dict) -> list:
    """从 API 返回数据中提取题目列表（尝试多种路径）。"""
    if not data:
        return []

    # 路径尝试（按优先级排列）
    paths = [
        ['solutions'],          # tiku.fenbi.com static/solution
        ['data', 'exercises'],
        ['data', 'exerciseVOs'],
        ['data', 'list'],
        ['data'],
        ['exercises'],
    ]

    for path in paths:
        d = data
        try:
            for key in path:
                d = d[key]
            if isinstance(d, list) and len(d) > 0:
                return d
        except (KeyError, TypeError, IndexError):
            continue

    # 如果 data 本身就是一个列表
    if isinstance(data.get('data'), list):
        return data['data']

    return []


def _build_index(data: dict, list_key: str = 'exercises') -> dict:
    """构建以 globalId / exerciseId / id 为 key 的索引字典。"""
    exercises = _extract_exercises(data)
    index = {}
    for ex in exercises:
        # 优先使用 globalId（新 API），其次 exerciseId、id
        eid = str(ex.get('globalId', ex.get('exerciseId', ex.get('id', ex.get('key', '')))))
        if eid:
            index[eid] = ex
    return index


def sanitize_filename(name: str) -> str:
    """将试卷名转换为安全的目录名。"""
    # 移除非法字符
    name = re.sub(r'[<>:"/\\|?*\s]+', '_', name)
    # 截断过长的名称
    if len(name) > 50:
        name = name[:50]
    return name.strip('_')


def save_report(questions: list[dict], exam_name: str = None, exam_date: str = '', materials: list = None) -> str:
    """保存合并后的报告到 data/reports/ 目录。

    目录格式：data/reports/YYYY-MM-DD_HH-MM-SS_<试卷名简称>/

    Args:
        questions: 合并后的题目列表
        exam_name: 试卷名称
        exam_date: 考试日期（从练习历史 API 获取）

    Returns:
        str: 保存的目录路径
    """
    now = datetime.now()
    timestamp = now.strftime('%Y-%m-%d_%H-%M-%S')

    if exam_name:
        # 使用 API 返回的真实试卷名（优先）
        pass
    if not exam_name and questions:
        # 兜底：从第一题的 source 推断试卷名
        first_source = questions[0].get('source', '')
        match = re.match(r'^(.*?)第\d+题', first_source)
        exam_name = match.group(1) if match else None

    # 目录名：优先用真实考试日期，其次用抓取时间戳
    dir_date = exam_date or timestamp[:10]
    safe_name = sanitize_filename(exam_name) if exam_name else 'unknown'
    dir_name = f"{dir_date}_{timestamp[11:]}_{safe_name}"
    base_dir = os.path.join(os.path.dirname(__file__), 'data', 'reports', dir_name)
    os.makedirs(base_dir, exist_ok=True)

    file_path = os.path.join(base_dir, 'merged_report.json')
    # 包装为包含元数据的结构
    payload = {
        'exam_date': exam_date,
        'exam_name': exam_name,
        'questions': questions,
    }
    if materials:
        payload['materials'] = materials
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n📁 报告已保存至：{file_path}")
    print(f"   共 {len(questions)} 道题目")
    if exam_date:
        print(f"   📅 考试日期：{exam_date}")
    return file_path


def main():
    parser = argparse.ArgumentParser(
        description='粉笔模考数据抓取工具 - 生成 merged_report.json'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--exam-key', '-k',
        help='试卷短 key，如 1_1_3jslr2e'
    )
    group.add_argument(
        '--url', '-u',
        help='完整的报告页面 URL（自动提取 exam key）'
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config()
    print("📋 配置已加载")

    # 获取 exam_key 和 routecs
    routecs = ''
    if args.url:
        exam_key, routecs = extract_exam_key_from_url(args.url)
        print(f"🔑 从 URL 提取到 exam_key：{exam_key}，routecs：{routecs}")
    else:
        exam_key = args.exam_key
        print(f"🔑 使用 exam_key：{exam_key}")

    # 步骤1：获取长 key 和用户答题数据
    solution_key, user_answers = get_solution_key(config, exam_key, routecs)

    # 步骤2：并发获取全部数据
    print("\n📡 并发获取三个接口数据...")
    api_results = fetch_all_data(config, exam_key, solution_key, routecs)

    # 步骤3：合并数据
    print("\n🔄 合并数据...")
    questions, materials = merge_data(api_results, user_answers)

    if not questions:
        print("❌ 合并后没有数据，请检查接口返回")
        sys.exit(1)

    # 步骤4：获取真实试卷名 + 考试日期
    exam_name = None
    static_data = api_results.get('static_solution', {}) or {}
    if isinstance(static_data, dict):
        exam_name = static_data.get('name', '')
        if exam_name:
            print(f"📝 试卷名称：{exam_name}")

    exam_date = fetch_exam_date(config, exam_key, routecs)
    if exam_date:
        print(f"📅 考试日期：{exam_date}")

    # 步骤5：保存
    report_path = save_report(questions, exam_name=exam_name, exam_date=exam_date, materials=materials)

    print(f"\n✅ 抓取完成！")
    print(f"   下一步：运行 python main.py analyze --report \"{report_path}\"")

    return report_path


def fetch_and_analyze(exam_input: str, cookie: str = '') -> dict:
    """供前端调用的完整抓取+分析流程。

    Args:
        exam_input: 试卷 URL 或 exam_key
        cookie: 粉笔 cookie（留空则用 config.yaml 中的）

    Returns:
        dict: {success, report_path, exam_name, exam_date, total_q, correct_q, error}
    """
    config = load_config()

    # 允许覆盖 cookie
    if cookie:
        config.setdefault('fenbi', {})['cookie'] = cookie

    # 解析 exam_key 和 routecs
    routecs = ''
    if 'fenbi.com' in exam_input or 'spa.fenbi' in exam_input:
        exam_key, routecs = extract_exam_key_from_url(exam_input)
    else:
        exam_key = exam_input.strip()

    try:
        # Step 1: 获取 solution key 和用户答题数据
        solution_key, user_answers = get_solution_key(config, exam_key, routecs)

        # Step 2: 并发获取数据
        api_results = fetch_all_data(config, exam_key, solution_key, routecs)

        # Step 3: 合并
        questions, materials = merge_data(api_results, user_answers)
        if not questions:
            return {'success': False, 'error': '合并后无题目数据'}

        # Step 4: 获取名称和日期
        static_data = api_results.get('static_solution', {}) or {}
        exam_name = static_data.get('name', '') if isinstance(static_data, dict) else ''
        exam_date = fetch_exam_date(config, exam_key, routecs)

        # Step 5: 保存
        report_path = save_report(questions, exam_name=exam_name, exam_date=exam_date, materials=materials)

        # Step 6: 自动入库分析
        from utils.analysis import process_report_for_init
        from utils.db import KnowledgeDB
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'knowledge_base.db')
        db = KnowledgeDB(db_path)
        result = process_report_for_init(report_path, db, diagnose_errors=False)

        total = len(questions)
        correct = sum(1 for q in questions if q.get('status') == 1)

        return {
            'success': result.get('success', False),
            'report_path': report_path,
            'exam_name': exam_name,
            'exam_date': exam_date,
            'total_q': total,
            'correct_q': correct,
            'error': result.get('error', ''),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == '__main__':
    main()
