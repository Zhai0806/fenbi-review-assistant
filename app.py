"""粉笔模考复盘工具 - Streamlit Web 界面

三栏布局：
- 左栏：复盘报告（模考选择、错题列表、蒙对/超时/连续错题标签页）
- 中栏：知识库洞察（模块卡片、薄弱知识点、图表）
- 右栏：AI 聊天（基于知识库的对话咨询）

用法：
    streamlit run app.py
"""

import json
import os
import re
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(__file__))

from utils.db import KnowledgeDB
from utils.analysis import (
    classify_module,
    detect_persistent_weak_points,
    generate_init_report,
    generate_incremental_report,
)
from utils.llm import chat_with_context


# ======================== 页面配置 ========================

st.set_page_config(
    page_title="粉笔模考复盘助手",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 自定义 CSS 美化
st.markdown("""
<style>
    .stApp { background-color: #f5f7fa; }
    .main-header { font-size: 1.8rem; font-weight: 700; color: #1a73e8; margin-bottom: 1rem; }
    .module-card {
        background: white; border-radius: 12px; padding: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 0.8rem;
    }
    .module-name { font-weight: 600; font-size: 1.1rem; color: #333; }
    .metric { font-size: 0.9rem; color: #666; }
    .metric-value { font-weight: 700; color: #1a73e8; }
    .error-row { background-color: #fff3f3; }
    .guessed-row { background-color: #fff8e1; }
    .anomaly-row { background-color: #fce4ec; }
    .consecutive-error { border-left: 4px solid #e53935; padding-left: 8px; }
</style>
""", unsafe_allow_html=True)


# ======================== 聊天记录持久化 ========================

CHAT_HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'data', 'chat_history.json')
CONV_NAMES = {"行测复盘","申论写作","备考规划","错题分析","面试准备","公基复习","随便聊聊"}


def _load_chat_data() -> dict:
    """加载聊天数据（多会话格式）。兼容旧版扁平列表。"""
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                # 旧版扁平列表 → 迁移为单个会话
                import time as _t
                data = {"conversations": [{"id": f"conv_{int(_t.time())}", "name": "旧对话", "messages": data}]}
            return data
        except (json.JSONDecodeError, IOError):
            pass
    return {"conversations": []}


def _save_chat_data(data: dict):
    """保存聊天数据。"""
    os.makedirs(os.path.dirname(CHAT_HISTORY_FILE), exist_ok=True)
    with open(CHAT_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _current_conv(data: dict) -> dict:
    """获取当前活跃会话。"""
    convs = data.get('conversations', [])
    if not convs:
        import time as _t
        conv = {"id": f"conv_{int(_t.time())}", "name": "行测复盘", "messages": []}
        data['conversations'] = [conv]
        return conv
    # 返回标记为 active 的，或第一个
    active = next((c for c in convs if c.get('active')), None)
    if not active:
        active = convs[-1]
        active['active'] = True
    return active


# ======================== 数据库初始化 ========================

@st.cache_resource
def get_db() -> KnowledgeDB:
    """获取数据库连接（缓存）。"""
    db_path = os.path.join(os.path.dirname(__file__), 'data', 'knowledge_base.db')
    return KnowledgeDB(db_path)


def _index_to_letter(idx) -> str:
    """将答案索引 '0'/'1'/'2'/'3' 转换为 'A'/'B'/'C'/'D'"""
    if idx is None:
        return '?'
    s = str(idx).strip()
    mapping = {'0': 'A', '1': 'B', '2': 'C', '3': 'D'}
    return mapping.get(s, s)


def _kp_breadcrumb(keypoints: list) -> str:
    """从知识点列表生成模块→题型→知识点 面包屑路径。"""
    if not keypoints:
        return ''
    from utils.analysis import classify_module, classify_question_type
    paths = []
    for kp in keypoints[:3]:
        name = kp.get('name', '') if isinstance(kp, dict) else str(kp)
        if not name:
            continue
        mod_map = classify_module([name])
        mod = next(iter(mod_map.keys()), '') if mod_map else ''
        qt = classify_question_type(name, mod) if mod else ''
        if qt and qt != mod:
            paths.append(f"{mod} → {qt} → {name}")
        elif mod:
            paths.append(f"{mod} → {name}")
        else:
            paths.append(name)
    return ' | '.join(paths)


def _question_label(q: dict, compact: bool = False, index: int = 0) -> str:
    """从题目数据中提取可读的题目标签。

    Args:
        q: 题目字典（含 source / question_key 字段）
        compact: True 时返回「第N题」
        index: 列表序号，compact 模式下的题号

    Returns:
        str: 题目标签
    """
    source = q.get('source', '')
    if compact:
        return f"第{index}题" if index > 0 else source[:20]
    return source if source else f"Q{q.get('question_key', '?')[:12]}"


# ======================== 左栏：复盘报告 ========================

def render_left_panel(db: KnowledgeDB):
    """渲染左栏：复盘报告。"""
    st.markdown('<div class="main-header">📋 复盘报告</div>', unsafe_allow_html=True)

    if 'selected_diags' not in st.session_state:
        st.session_state['selected_diags'] = {}
    if 'current_exam_context' not in st.session_state:
        st.session_state['current_exam_context'] = ''

    # ── 抓取新模考 ──
    with st.expander("📥 抓取新模考数据", expanded=False):
        exam_input = st.text_input("试卷 URL 或 Exam Key", placeholder="https://spa.fenbi.com/... 或 1_1_3jslr2e")
        cookie_input = st.text_input("Cookie（留空使用 config.yaml）", placeholder="sid=...", type="password")
        if st.button("🚀 开始抓取并分析", type="primary", disabled=not exam_input):
            with st.spinner("抓取中..."):
                from fetch import fetch_and_analyze
                result = fetch_and_analyze(exam_input, cookie_input)
            if result['success']:
                st.success(f"✅ {result['exam_name'][:30]} — {result['total_q']}题，正确{result['correct_q']}题，日期{result['exam_date']}")
                st.caption("刷新页面即可在下方选择新报告")
            else:
                st.error(f"❌ {result.get('error', '抓取失败')}")

    # 选择模考记录
    exams = db.get_exam_records()
    if not exams:
        st.info("暂无模考记录。请先运行 `python main.py init --data-dir <目录>` 初始化知识库。")
        return

    exam_options = {f"{e['exam_date']} - {e['exam_name'][:30]}": e for e in exams}
    selected_label = st.selectbox("选择模考记录", list(exam_options.keys()))
    selected_exam = exam_options[selected_label]

    report_path = selected_exam['report_path']

    # 保存当前考试上下文，供 AI 对话使用
    total_t = selected_exam.get('total_time_sec', 0) or 0
    st.session_state['current_exam_context'] = (
        f"当前选中报告：{selected_exam['exam_name']}，"
        f"日期：{selected_exam['exam_date']}，"
        f"共{selected_exam['total_questions']}题，"
        f"正确{selected_exam['correct_questions']}题，"
        f"正确率{selected_exam['correct_questions']/max(selected_exam['total_questions'],1):.1%}，"
        f"总用时{int(total_t//60)}分{int(total_t%60)}秒"
    )

    # 基本统计
    total_time = selected_exam.get('total_time_sec', 0) or 0
    time_str = f"{int(total_time // 60)}分{int(total_time % 60)}秒" if total_time else '未知'
    st.markdown(f"""
    <div class="module-card">
        <div class="module-name">{selected_exam['exam_name']}</div>
        <span class="metric">日期：{selected_exam['exam_date']} |
        正确率：{selected_exam['correct_questions']}/{selected_exam['total_questions']}
        （{selected_exam['correct_questions']/max(selected_exam['total_questions'], 1):.1%}）|
        总用时：{time_str}</span>
    </div>
    """, unsafe_allow_html=True)

    # 获取该报告的题目
    questions = db.get_questions_by_report(report_path)

    if not questions:
        st.warning("该报告暂无题目分析数据。")
        return

    # 模块用时分析（需要原始报告的 keypoints 来分类模块）
    import json as _json, os as _os
    raw_questions = questions  # fallback
    if _os.path.exists(report_path):
        try:
            with open(report_path, 'r', encoding='utf-8') as _f:
                _data = _json.load(_f)
            if isinstance(_data, dict):
                raw_questions = _data.get('questions', _data.get('data', []))
            elif isinstance(_data, list):
                raw_questions = _data
            else:
                raw_questions = []
        except Exception:
            pass

    from utils.analysis import analyze_module_timing
    timing = analyze_module_timing(raw_questions)
    if timing:
        with st.expander("⏱️ 各模块用时分析", expanded=False):
            for t in timing:
                st.markdown(
                    f"{t['verdict']} **{t['module']}**（{t['question_count']}题）："
                    f"实际 {t['actual_min']:.1f}分 / 预算 {t['budget_min']:.1f}分 "
                    f"（{t['ratio']:.0%}）"
                )
                st.caption(f"   💡 {t['advice']}")
            st.caption("预算按标准考场时间分配：常识~35秒/题、言语~52秒/题、数量~70秒/题、判断~55秒/题、资料~75秒/题")

    # 标签页
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 全部题目", "❌ 错题列表",
        "🎯 蒙对/超时", "🔴 连续错题"
    ])

    with tab1:
        _render_all_questions(questions, db)

    with tab2:
        _render_wrong_questions(questions, db, report_path)

    with tab3:
        _render_anomaly_questions(questions)

    with tab4:
        _render_persistent_weak_points(db)


def _render_wrong_q_bank(db: KnowledgeDB, current_report_path: str = ''):
    """错题本：跨考聚合 + 模块筛选 + 乱序 + 计时 + 交互答题。"""
    import random as _random
    import time as _time

    st.markdown("### 📖 错题本")
    st.caption("聚合所有考试的错题，可筛选模块、乱序出题、计时作答")

    # 收集所有错题
    all_wrong = []
    exams = db.get_exam_records()
    for exam in exams:
        rp = exam['report_path']
        if not os.path.exists(rp):
            continue
        try:
            with open(rp, 'r', encoding='utf-8') as f:
                data = json.load(f)
            qs = data if isinstance(data, list) else data.get('questions', [])
            for q in qs:
                if not isinstance(q, dict):
                    continue
                if q.get('status') != -1:
                    continue
                kps = q.get('keypoints', [])
                kp_names = [k.get('name', '') for k in kps]
                from utils.analysis import classify_module
                mod_map = classify_module(list(set(kp_names))) if kp_names else {}
                mod = next(iter(mod_map.keys()), '其他') if mod_map else '其他'
                qa = db.get_question_by_key(q.get('key', ''))
                all_wrong.append({
                    'exam_name': exam['exam_name'], 'exam_date': exam['exam_date'],
                    'source': q.get('source', ''), 'key': q.get('key', ''),
                    'content': q.get('content', ''), 'options': q.get('options', []),
                    'your_answer': qa.get('your_answer', '') if qa else q.get('your_answer', ''),
                    'correct_answer': qa.get('correct_answer', '') if qa else q.get('correct_answer', ''),
                    'module': mod,
                    'error_type': qa.get('error_type', '') if qa else '',
                    'time_spent_sec': q.get('time_spent_sec', 0),
                    'materialKeys': q.get('materialKeys', []),
                })
        except Exception:
            continue

    if not all_wrong:
        st.info("暂无错题数据。")
        return

    # 筛选
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        modules = sorted(set(q['module'] for q in all_wrong))
        sel_mod = st.selectbox("筛选模块", ["全部"] + modules, key="wqb_mod")
    with col_f2:
        max_q = st.slider("每次题量", 5, min(50, len(all_wrong)), 10, key="wqb_count")
    with col_f3:
        shuffle_on = st.checkbox("🔀 乱序", value=True, key="wqb_shuffle")

    # 过滤 + 乱序
    pool = [q for q in all_wrong if sel_mod == "全部" or q['module'] == sel_mod]
    if shuffle_on:
        _random.shuffle(pool)
    pool = pool[:max_q]

    if 'wqb_index' not in st.session_state:
        st.session_state['wqb_index'] = 0
        st.session_state['wqb_score'] = 0
        st.session_state['wqb_start_time'] = _time.time()

    idx = st.session_state['wqb_index']
    if idx >= len(pool):
        elapsed = _time.time() - st.session_state['wqb_start_time']
        score = st.session_state['wqb_score']
        st.success(f"🎉 完成！{score}/{len(pool)} 正确（{score/max(len(pool),1):.0%}），用时 {int(elapsed//60)}分{int(elapsed%60)}秒")
        if st.button("🔄 重新开始", key="wqb_restart"):
            del st.session_state['wqb_index'], st.session_state['wqb_score'], st.session_state['wqb_start_time']
            st.rerun()
        return

    q = pool[idx]
    elapsed = _time.time() - st.session_state['wqb_start_time']
    st.progress(idx / len(pool), f"第 {idx+1}/{len(pool)} 题 | 用时 {int(elapsed//60)}:{int(elapsed%60):02d} | 正确 {st.session_state['wqb_score']}/{idx}")
    st.caption(f"📂 {q['module']} | 📅 {q['exam_date']} {q['exam_name'][:15]} | ⏱ 原用时 {q['time_spent_sec']}秒")

    q_html = q.get('content', '')
    if q_html:
        q_html = q_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")
        st.markdown(q_html, unsafe_allow_html=True)

    from utils.llm import _strip_html as _shb
    opts = q.get('options', [])
    opt_labels = [f"{chr(65+j)}. {_shb(o)[:80]}" for j, o in enumerate(opts[:4])]
    choice = st.radio("你的选择：", opt_labels, key=f"wqb_{idx}", index=None)

    if choice and st.button("✅ 提交", key=f"wqb_submit_{idx}", type="primary"):
        picked = str(opt_labels.index(choice))
        correct = str(q.get('correct_answer', ''))
        if picked == correct:
            st.session_state['wqb_score'] += 1
            st.success(f"✅ 正确！")
        else:
            st.error(f"❌ 你选 {choice[0]}，正确 {_index_to_letter(correct)} | 原错因：{q.get('error_type', '-')}")
        st.session_state['wqb_index'] += 1
        st.rerun()

    if st.button("⏭ 跳过", key=f"wqb_skip_{idx}"):
        st.session_state['wqb_index'] += 1
        st.rerun()


def _render_all_questions(questions: list[dict], db: KnowledgeDB):
    """渲染全部题目表格。"""
    if not questions:
        st.info("无题目数据")
        return

    # 构造表格数据
    rows = []
    for i, q in enumerate(questions, 1):
        is_wrong = not q.get('is_correct', True)
        row_style = 'error-row' if is_wrong else ''

        ratio = q.get('global_correct_ratio', 0) or 0
        rows.append({
            '序号': i,
            '题目来源': _question_label(q, compact=True, index=i),
            '你的答案': _index_to_letter(q.get('your_answer')),
            '正确答案': _index_to_letter(q.get('correct_answer')),
            '结果': '❌' if is_wrong else '✅',
            '用时(秒)': q.get('time_spent_sec') or '-',
            '全站正确率': f"{ratio * 100:.1f}%",
            '错误类型': q.get('error_type') or '-',
            '蒙对': '🎯' if q.get('is_guessed_correct') else '',
            '超时': '⏰' if q.get('is_time_anomaly') else '',
        })

    df = pd.DataFrame(rows)

    # 应用行样式
    def highlight_errors(row):
        if row['结果'] == '❌':
            return ['background-color: #fff3f3'] * len(row)
        return [''] * len(row)

    styled = df.style.apply(highlight_errors, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _render_wrong_questions(questions: list[dict], db: KnowledgeDB, report_path: str = ''):
    """渲染错题列表（AI 诊断 → 批量确认 → 学习建议 → 手动微调）。"""
    wrong_qs = [q for q in questions if not q.get('is_correct', True)]

    if not wrong_qs:
        st.success("🎉 全部正确！")
        return

    # 按题号排序（DB 存储顺序是模块分组，不是考试题号序）
    import re as _re
    wrong_qs.sort(key=lambda q: int(_re.search(r'第(\d+)题', q.get('source', '')).group(1))
                  if _re.search(r'第(\d+)题', q.get('source', '')) else 9999)

    valid_error_types = [
        '计算失误', '公式用错', '概念混淆', '审题不清',
        '时间不足蒙的', '记忆盲区', '放弃', '其他'
    ]

    # ── AI 诊断区 ──
    pending = db.get_pending_diagnoses(report_path) if report_path else []
    unlabeled = sum(1 for q in wrong_qs if not q.get('error_type') or q['error_type'] == '其他')

    st.markdown(f"共 **{len(wrong_qs)}** 道错题 | "
                f"📝 {unlabeled} 未标注 | "
                f"📋 {len(pending)} 待确认")

    col1, col2 = st.columns([1, 2])
    with col1:
        batches_est = max(1, (unlabeled + 4) // 5)
        cost_est = batches_est * 0.005  # ~¥0.005/batch
        if st.button(
            f"🤖 AI 诊断 ({unlabeled}题 · ~¥{cost_est:.2f})",
            type="primary",
            disabled=unlabeled == 0,
            key=f"ai_diag_{report_path[-20:]}"
        ):
            with st.spinner(f"批量诊断中（{batches_est} 批，约 {batches_est*3} 秒）..."):
                from utils.analysis import diagnose_report_errors
                result = diagnose_report_errors(db, report_path)
                st.toast(f"✅ {result.get('diagnosed', 0)} 道已诊断"
                        f"（{result.get('batches', '?')} 批），"
                        f"跳过 {result.get('skipped', 0)} 道")
                st.rerun()
    with col2:
        labeled = len(wrong_qs) - unlabeled
        if labeled > 0:
            st.caption(f"📌 {labeled} 道已有标注，无需重复诊断")
        if unlabeled > 0:
            st.caption(f"💡 {unlabeled} 道待诊断 · 5题/批 ≈ {batches_est} 次调用 · ~¥{cost_est:.2f}")
        if pending:
            st.caption("确认诊断后可查看个性化学习方案")

    # ── 确认区 ──
    if pending:
        # 按题号排序
        def _pn(p):
            qa = db.get_question_by_key(p['question_key'])
            m = re.search(r'第(\d+)题', qa.get('source', '') if qa else '')
            return int(m.group(1)) if m else 9999
        pending.sort(key=_pn)

        # 预加载原始题目数据和材料
        raw_qs = {}
        raw_materials = {}
        try:
            with open(report_path, 'r', encoding='utf-8') as _f:
                _d = json.load(_f)
            _list = _d if isinstance(_d, list) else _d.get('questions', _d.get('data', []))
            raw_qs = {q.get('key', ''): q for q in _list if isinstance(q, dict)}
            _mats = _d.get('materials', []) if isinstance(_d, dict) else []
            raw_materials = {str(m.get('globalId', m.get('id', ''))): m for m in _mats if isinstance(m, dict)}
        except Exception:
            pass

        st.markdown("---")
        st.markdown("### 📋 确认 AI 诊断")

        # 批量操作
        all_ids = {p['id']: p['error_type'] for p in pending}
        selected = st.session_state.get('selected_diags', {})
        all_selected = all_ids and all(pid in selected for pid in all_ids)

        col_select, col_confirm = st.columns([1, 1])
        with col_select:
            btn_label = "⬜ 取消全选" if all_selected else "☑️ 全选"
            if st.button(btn_label, key="toggle_all_diag"):
                if all_selected:
                    st.session_state['selected_diags'] = {}
                else:
                    st.session_state['selected_diags'] = dict(all_ids)
                st.rerun()
        with col_confirm:
            n_selected = len(selected)
            if st.button(f"✅ 确认 {n_selected} 条" if n_selected else "✅ 确认",
                         type="primary", disabled=n_selected == 0):
                for pid, etype in selected.items():
                    db.confirm_diagnosis(pid, final_error_type=etype)
                st.session_state['selected_diags'] = {}
                st.toast(f"✅ 已确认 {n_selected} 条")
                st.rerun()

        # 按共享材料分组
        material_groups = {}  # materialKey -> list of pending items
        standalone = []       # 无材料的独立题
        for p in pending:
            rq = raw_qs.get(p['question_key'], {})
            mks = rq.get('materialKeys', []) if rq else []
            if mks:
                for mk in mks:
                    material_groups.setdefault(str(mk), []).append(p)
            else:
                standalone.append(p)

        pi = 0  # 全局题号
        # 先渲染材料组
        for mk, group_items in material_groups.items():
            pi += 1
            mat = raw_materials.get(mk, {})
            mat_html = mat.get('content', '')
            if mat_html:
                mat_html = mat_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")

            # 计算组内标题
            group_labels = []
            for p in group_items:
                qa = db.get_question_by_key(p['question_key'])
                group_labels.append(_question_label({'source': qa.get('source', '') if qa else '', 'question_key': p['question_key']}, compact=True, index=pi))
            title = '、'.join(group_labels)

            with st.expander(
                f"{title} — 共享材料题（{len(group_items)}道错题）",
                expanded=(pi <= 2)
            ):
                # 材料内容
                if mat_html:
                    with st.container(border=True):
                        st.markdown(mat_html, unsafe_allow_html=True)

                # 逐题渲染
                for p in group_items:
                    qa = db.get_question_by_key(p['question_key'])
                    if not qa:
                        continue
                    pid = p['id']
                    rq = raw_qs.get(p['question_key'], {})
                    checked = pid in selected

                    q_html = rq.get('content', '') if rq else ''
                    if q_html:
                        q_html = q_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")
                    from utils.llm import _strip_html
                    opts = rq.get('options', []) if rq else []
                    opt_str = ' | '.join(f'{chr(65+j)}. {_strip_html(o)[:40]}' for j, o in enumerate(opts[:4]))

                    with st.container(border=True):
                        if q_html:
                            st.markdown(q_html, unsafe_allow_html=True)
                        if opt_str:
                            st.caption(f"📋 {opt_str}")
                        kp_path = _kp_breadcrumb(rq.get('keypoints', [])) if rq else ''
                        if kp_path:
                            st.caption(f"🏷 {kp_path}")
                        st.caption(
                            f"🖊 你的：{_index_to_letter(qa.get('your_answer'))}  |  "
                            f"✅ 正确：{_index_to_letter(qa.get('correct_answer'))}  |  "
                            f"💬 AI：{p['error_type']}（{p['confidence']:.0%}）{p['explanation']}"
                        )
                        cc1, cc2, cc3 = st.columns([2, 2, 1])
                        with cc1:
                            if st.checkbox("采纳", value=checked, key=f"chk_{pid}"):
                                st.session_state.setdefault('selected_diags', {})[pid] = p['error_type']
                            elif pid in st.session_state.get('selected_diags', {}):
                                del st.session_state['selected_diags'][pid]
                        with cc2:
                            new_type = st.selectbox("类型", valid_error_types,
                                index=valid_error_types.index(p['error_type']) if p['error_type'] in valid_error_types else -1,
                                key=f"ct_{pid}", label_visibility="collapsed")
                            if new_type != p['error_type']:
                                st.session_state.setdefault('selected_diags', {})[pid] = new_type
                        with cc3:
                            if st.button("✅", key=f"ok_{pid}"):
                                db.confirm_diagnosis(pid, final_error_type=new_type)
                                st.session_state.setdefault('selected_diags', {}).pop(pid, None)
                                st.rerun()

        # 再渲染独立题
        for p in standalone:
            pi += 1
            qa = db.get_question_by_key(p['question_key'])
            if not qa:
                continue
            pid = p['id']
            rq = raw_qs.get(p['question_key'], {})
            checked = pid in selected

            q_html = rq.get('content', '') if rq else ''
            if q_html:
                q_html = q_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")
            opts = rq.get('options', []) if rq else []
            from utils.llm import _strip_html
            opt_str = ' | '.join(f'{chr(65+j)}. {_strip_html(o)[:40]}' for j, o in enumerate(opts[:4]))
            label = _question_label({'source': qa.get('source', ''), 'question_key': p['question_key']}, compact=True, index=pi)

            with st.expander(
                f"{label} — 🤖 {p['error_type']}（{p['confidence']:.0%}）{'✅ 已选' if checked else ''}",
                expanded=(pi <= 2)
            ):
                if q_html:
                    st.markdown(q_html, unsafe_allow_html=True)
                if opt_str:
                    st.caption(f"📋 {opt_str}")
                kp_path = _kp_breadcrumb(rq.get('keypoints', [])) if rq else ''
                if kp_path:
                    st.caption(f"🏷 {kp_path}")
                st.caption(
                    f"🖊 你的：{_index_to_letter(qa.get('your_answer'))}  |  "
                    f"✅ 正确：{_index_to_letter(qa.get('correct_answer'))}  |  "
                    f"💬 AI：{p['explanation']}"
                )
                cc1, cc2, cc3 = st.columns([2, 2, 1])
                with cc1:
                    if st.checkbox("采纳", value=checked, key=f"chk_{pid}"):
                        st.session_state.setdefault('selected_diags', {})[pid] = p['error_type']
                    elif pid in st.session_state.get('selected_diags', {}):
                        del st.session_state['selected_diags'][pid]
                with cc2:
                    new_type = st.selectbox("类型", valid_error_types,
                        index=valid_error_types.index(p['error_type']) if p['error_type'] in valid_error_types else -1,
                        key=f"ct_{pid}", label_visibility="collapsed")
                    if new_type != p['error_type']:
                        st.session_state.setdefault('selected_diags', {})[pid] = new_type
                with cc3:
                    if st.button("✅", key=f"ok_{pid}"):
                        db.confirm_diagnosis(pid, final_error_type=new_type)
                        st.session_state.setdefault('selected_diags', {}).pop(pid, None)
                        st.rerun()

        return  # 有待确认项时，不显示下面的手动列表

    # ── 学习建议 ──
    labeled = sum(1 for q in wrong_qs if q.get('error_type') and q['error_type'] != '其他')
    if labeled >= len(wrong_qs) * 0.5:
        # 每日复习日程
        from collections import Counter
        et_counts = Counter(q.get('error_type', '其他') for q in wrong_qs if q.get('error_type') and q['error_type'] != '其他')
        top_et = et_counts.most_common(3)
        if top_et:
            st.markdown("### 📅 本周复习计划")
            st.markdown(
                f"- **今日**：重做本卷 {len(wrong_qs)} 道错题（重做模式），每题写错因总结\n"
                f"- **明天**：针对「{top_et[0][0]}」做 10 道同类题\n"
                + (f"- **后天**：针对「{top_et[1][0]}」做 10 道同类题\n" if len(top_et) > 1 else "") +
                f"- **周末**：完整复盘本卷，标记仍有困难的知识点"
            )
        _render_learning_advice(wrong_qs, db)

    # ── 手动微调列表 ──
    st.markdown("---")
    retry_mode = st.checkbox("🔄 重做模式（交互答题）", key="retry_mode")

    # 预加载原始题目
    retry_raw = {}
    try:
        with open(report_path, 'r', encoding='utf-8') as _f:
            _d = json.load(_f)
        _list = _d if isinstance(_d, list) else _d.get('questions', _d.get('data', []))
        retry_raw = {q.get('key', ''): q for q in _list if isinstance(q, dict)}
    except Exception:
        pass

    from utils.llm import _strip_html as _sh

    for i, q in enumerate(wrong_qs, 1):
        current_type = q.get('error_type') or '其他'
        rq = retry_raw.get(q['question_key'], {})
        label = _question_label(q, compact=True, index=i)

        if retry_mode:
            # 交互重做模式
            with st.expander(f"{label} | 重做中...", expanded=(i <= 1)):
                q_html = rq.get('content', '') if rq else ''
                if q_html:
                    q_html = q_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")
                    st.markdown(q_html, unsafe_allow_html=True)
                opts = rq.get('options', []) if rq else []
                if opts:
                    opt_labels = [f"{chr(65+j)}. {_sh(o)[:60]}" for j, o in enumerate(opts[:4])]
                    choice = st.radio("你的选择：", opt_labels, key=f"retry_{q['question_key']}", index=None,
                                      format_func=lambda x: x)
                    if choice and st.button("提交", key=f"submit_{q['question_key']}"):
                        picked = str(opt_labels.index(choice))
                        correct = str(q.get('correct_answer', ''))
                        if picked == correct:
                            st.success(f"✅ 正确！答案就是 {choice[0]}")
                        else:
                            st.error(f"❌ 选 {choice[0]}，正确是 {_index_to_letter(correct)}")
                        st.caption(f"💡 原错因：{current_type}")
        else:
            # 普通模式
            with st.expander(
                f"{label} | 你的：{_index_to_letter(q.get('your_answer'))} → "
                f"正确：{_index_to_letter(q.get('correct_answer'))} | {current_type}",
                expanded=False
            ):
                q_html = rq.get('content', '') if rq else ''
                if q_html:
                    q_html = q_html.replace('src="//', 'src="https://').replace("src='//", "src='https://")
                    st.markdown(q_html, unsafe_allow_html=True)
                opts = rq.get('options', []) if rq else []
                if opts:
                    from utils.llm import _strip_html as _sh3
                    opt_str = ' | '.join(f'{chr(65+j)}. {_sh3(o)[:60]}' for j, o in enumerate(opts[:4]))
                    st.caption(f"📋 {opt_str}")
                st.caption(
                    f"🖊 你的：{_index_to_letter(q.get('your_answer'))}  |  "
                    f"✅ 正确：{_index_to_letter(q.get('correct_answer'))}"
                )

            col1, col2 = st.columns([1, 1])
            with col1:
                try:
                    type_idx = valid_error_types.index(current_type)
                except ValueError:
                    type_idx = len(valid_error_types) - 1
                new_type = st.selectbox(
                    "错误类型", valid_error_types, index=type_idx,
                    key=f"mt_{q['question_key']}"
                )
                if new_type != current_type:
                    db.update_question_field(q['question_key'], 'error_type', new_type)
                    if report_path:
                        db._sync_kp_error_type(report_path, q['question_key'], new_type)
                    st.toast(f"✅ {new_type}")
            with col2:
                current_note = q.get('user_note', '')
                new_note = st.text_area(
                    "备注", value=current_note, height=68,
                    key=f"note_{q['question_key']}", placeholder="反思..."
                )
                if new_note != current_note:
                    db.update_question_field(q['question_key'], 'user_note', new_note)

    # ── 导出 ──
    st.markdown("---")
    from utils.llm import _strip_html as _sh
    export_text = "# 错题清单\n\n"
    for i, q in enumerate(wrong_qs, 1):
        et = q.get('error_type') or '其他'
        rq = retry_raw.get(q['question_key'], {})
        # 材料
        mat_keys = rq.get('materialKeys', []) if rq else []
        mat_content = ''
        for mk in mat_keys:
            mat = retry_raw.get('_materials', {}).get(str(mk), {})
            if not mat and raw_materials if 'raw_materials' in dir() else {}:
                pass  # skip complex material lookup in export
            break  # materials not easily accessible here, skip for export
        # 题目内容
        content = _sh(rq.get('content', ''))[:500] if rq else ''
        opts = rq.get('options', []) if rq else []
        opt_text = '\n'.join(f"{chr(65+j)}. {_sh(o)[:80]}" for j, o in enumerate(opts[:4]))
        kp_path = _kp_breadcrumb(rq.get('keypoints', [])) if rq else ''
        export_text += (
            f"## {i}. {q.get('source', '')}\n"
            f"**知识点**：{kp_path}\n\n"
            f"**题目**：{content}\n\n"
            f"**选项**：\n{opt_text}\n\n"
            f"- 你的答案：{_index_to_letter(q.get('your_answer'))} | "
            f"正确答案：{_index_to_letter(q.get('correct_answer'))}\n"
            f"- 错误类型：{et} | 用时：{q.get('time_spent_sec', '-')}秒\n"
            f"- 全站正确率：{(q.get('global_correct_ratio', 0) or 0) * 100:.1f}%\n\n"
            f"---\n\n"
        )
    st.download_button(
        "📥 导出错题清单", export_text,
        file_name="错题清单.md", mime="text/markdown"
    )


def _llm_available():
    try:
        from utils.llm import _load_llm_config
        cfg = _load_llm_config()
        return bool(cfg.get('api_key') or os.environ.get('DEEPSEEK_API_KEY'))
    except Exception:
        return False


def _render_notes(db: KnowledgeDB):
    """笔记页面：增删改查。"""
    st.markdown("### 📝 备考笔记")
    notes = db.get_all_notes()

    # 新增笔记
    with st.expander("➕ 新建笔记", expanded=not notes):
        n_title = st.text_input("标题", key="new_note_title")
        n_content = st.text_area("内容", key="new_note_content", height=150)
        if st.button("保存笔记", key="save_note") and n_title:
            db.upsert_note(title=n_title, content=n_content)
            st.rerun()

    if not notes:
        st.info("暂无笔记")
        return

    for n in notes:
        with st.expander(f"📌 {n.get('title', '无标题')} — {n.get('updated_at', '')[:10]}"):
            st.markdown(n.get('content', ''))
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🗑 删除", key=f"del_note_{n['id']}"):
                    db.delete_note(n['id'])
                    st.rerun()
            with c2:
                new_content = st.text_area("编辑内容", value=n.get('content', ''), key=f"edit_note_{n['id']}")
                if new_content != n.get('content', ''):
                    db.upsert_note(note_id=n['id'], title=n.get('title', ''), content=new_content)
                    st.toast("已更新")


def _render_links(db: KnowledgeDB):
    """自定义链接管理。"""
    import json as _j
    import os as _os
    links_file = _os.path.join(_os.path.dirname(__file__), 'data', 'custom_links.json')
    if _os.path.exists(links_file):
        with open(links_file, 'r', encoding='utf-8') as f:
            links = _j.load(f)
    else:
        links = []

    st.markdown("### 🔗 学习链接")
    for i, link in enumerate(links):
        st.markdown(f"- [{link['name']}]({link['url']})  `{link.get('desc', '')}`")
        if st.button("🗑", key=f"del_link_{i}"):
            links.pop(i)
            with open(links_file, 'w', encoding='utf-8') as f:
                _j.dump(links, f, ensure_ascii=False, indent=2)
            st.rerun()

    with st.expander("➕ 添加链接"):
        l_name = st.text_input("名称", key="new_link_name", placeholder="B站-小马哥公基")
        l_url = st.text_input("URL", key="new_link_url", placeholder="https://...")
        l_desc = st.text_input("备注", key="new_link_desc")
        if st.button("添加") and l_name and l_url:
            links.append({'name': l_name, 'url': l_url, 'desc': l_desc})
            _os.makedirs(_os.path.dirname(links_file), exist_ok=True)
            with open(links_file, 'w', encoding='utf-8') as f:
                _j.dump(links, f, ensure_ascii=False, indent=2)
            st.rerun()


def _render_learning_advice(wrong_qs: list[dict], db: KnowledgeDB):
    """基于真实错题数据生成可执行的学习方案。"""
    from collections import Counter, defaultdict

    # 从 DB 获取模块→题型→错误类型分布
    by_module = db.get_error_type_by_module()
    if not by_module:
        return

    st.markdown("### 🧠 个性化学习方案")
    st.caption("基于你的错题数据自动生成，不是泛化的模板建议")

    # 按模块聚合
    mod_error = defaultdict(lambda: defaultdict(int))
    mod_total = defaultdict(int)
    for r in by_module:
        if r['error_type'] == '其他':
            continue
        mod_error[r['module']][r['error_type']] += r['count']
        mod_total[r['module']] += r['count']

    # 错误类型→认知策略
    strategy = {
        '记忆盲区': ('间隔重复', '闪卡回忆，按 1-3-7-14 天间隔'),
        '计算失误': ('限时速算', '每天 10 道限时计算，用草稿纸分区'),
        '概念混淆': ('对比辨析', '做概念对比表，用费曼法讲出来'),
        '审题不清': ('圈画训练', '读题时笔圈否定词和提问词'),
        '公式用错': ('检索默写', '不看书默公式→核对→做变式题'),
        '时间不足蒙的': ('节奏控制', '2分钟无思路果断跳，先易后难'),
        '放弃': ('微习惯', '每天只做 2 道该模块题，先建立信心'),
    }

    # 按总错题数排序模块
    sorted_mods = sorted(mod_total.items(), key=lambda x: -x[1])

    for mod, total_err in sorted_mods:
        if total_err < 3:
            continue
        err_types = mod_error[mod]
        top_err = max(err_types, key=err_types.get) if err_types else None
        if not top_err:
            continue

        strat_name, strat_desc = strategy.get(top_err, ('针对性练习', '逐题分析错因'))

        with st.expander(
            f"**{mod}**（{total_err} 道错题 · 主要问题：{top_err}）",
            expanded=(total_err >= 8)
        ):
            # 主要错误类型分布
            sorted_errs = sorted(err_types.items(), key=lambda x: -x[1])
            err_str = ' | '.join(f'{et}×{c}' for et, c in sorted_errs[:4])
            st.markdown(f"**错误分布**：{err_str}")

            # 核心策略
            st.markdown(f"**🎯 核心策略**：{strat_name} — {strat_desc}")

            # 可执行的周计划
            st.markdown("**📅 本周行动计划**：")
            if mod in ('常识判断', '政治理论'):
                st.markdown(
                    f"- 每天早上通勤时用闪卡复习该模块知识点（15 分钟）\n"
                    f"- 睡前回顾当天错题涉及的 {sorted_errs[0][0] if sorted_errs else '知识点'}（5 分钟）\n"
                    f"- 周末集中做 1 套该模块专项练习，标记反复出错的点"
                )
            elif mod in ('资料分析', '数量关系'):
                st.markdown(
                    f"- 每天午饭后限时做 5 道 {mod} 题（15 分钟），记录每道耗时\n"
                    f"- 错题分析：区分「不会做」vs「算错了」，分别记录\n"
                    f"- 周末复盘本周计算失误点，总结高频易错公式"
                )
            elif mod in ('言语理解与表达', '判断推理'):
                st.markdown(
                    f"- 每天下午做 5 道 {mod} 题，每道写一句话概括解题逻辑\n"
                    f"- 错题用「我为什么选 X 而不是 Y」自我解释，写到备注里\n"
                    f"- 周末把同类型错题放一起对比，找出共同的迷惑选项特征"
                )

            # 认知科学提示
            st.caption(
                "📖 认知原理：**间隔重复**防止遗忘曲线下降；**交错练习**提升迁移能力；"
                "**自我解释**强化元认知。详见《认知天性》《学习之道》。"
            )


def _render_anomaly_questions(questions: list[dict]):
    """渲染蒙对题和超时题。"""
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("### 🎯 蒙对题")
        guessed = [q for q in questions if q.get('is_guessed_correct')]
        if not guessed:
            st.info("无蒙对题")
        else:
            st.metric("蒙对题数", len(guessed))
            for gi, q in enumerate(guessed, 1):
                gr = q.get('global_correct_ratio', 0) or 0
                st.markdown(
                    f"- {_question_label(q, compact=True, index=gi)} | "
                    f"答案：{_index_to_letter(q.get('your_answer'))} | "
                    f"用时：{q.get('time_spent_sec', '-')}秒 | "
                    f"全站：{gr * 100:.1f}%"
                )

    with col_b:
        st.markdown("### ⏰ 超时题")
        anomaly = [q for q in questions if q.get('is_time_anomaly')]
        if not anomaly:
            st.info("无超时题")
        else:
            st.metric("超时题数", len(anomaly))
            for ai, q in enumerate(anomaly, 1):
                st.markdown(
                    f"- {_question_label(q, compact=True, index=ai)} | "
                    f"用时：{q.get('time_spent_sec', '-')}秒 | "
                    f"结果：{'✅' if q.get('is_correct') else '❌'}"
                )


def _render_persistent_weak_points(db: KnowledgeDB):
    """渲染跨考持续薄弱知识点（在连续考试中都出错的知识点）。"""
    persistent = detect_persistent_weak_points(db, min_consecutive=2)

    if not persistent:
        st.info("数据不足：需要至少 2 次有错题的考试才能分析跨考薄弱趋势。")
        return

    st.markdown("### 🔴 跨考持续薄弱知识点")
    st.caption("在连续多次考试中都出现错误的知识点，是需要重点攻克的真正短板。")

    # 按严重程度分级
    critical = [p for p in persistent if p['streak'] >= 3]
    warning = [p for p in persistent if p['streak'] == 2]

    if critical:
        st.error(f"🚨 **高危** — 连续 ≥3 次考试出错（{len(critical)} 个知识点）")
        for p in critical:
            exam_names = ' → '.join(e['exam_name'][:16] for e in p['exams'])
            qt = p.get('question_type', '') or p['module']
            st.markdown(
                f"- **{p['point_name']}**（{p['module']} → {qt}）"
                f"  \n  📅 连续 {p['streak']} 次：{exam_names}"
            )

    if warning:
        st.warning(f"⚠️ **关注** — 连续 2 次考试出错（{len(warning)} 个知识点）")
        for p in warning:
            exam_names = ' → '.join(e['exam_name'][:16] for e in p['exams'])
            qt = p.get('question_type', '') or p['module']
            st.markdown(
                f"- **{p['point_name']}**（{p['module']} → {qt}）"
                f"  \n  📅 连续 {p['streak']} 次：{exam_names}"
            )


# ======================== 中栏：知识库洞察 ========================

def render_middle_panel(db: KnowledgeDB):
    """渲染中栏：知识库洞察。"""
    st.markdown('<div class="main-header">📊 知识库洞察</div>', unsafe_allow_html=True)

    # 子标签页
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 模块概览", "🎯 薄弱知识点", "📉 趋势分析", "🔬 错误分布"
    ])

    with tab1:
        _render_module_overview(db)
    with tab2:
        _render_weak_points(db)
    with tab3:
        _render_trend_analysis(db)
    with tab4:
        _render_error_distribution(db)


def _render_module_overview(db: KnowledgeDB):
    """渲染模块卡片（含题型分解）。"""
    type_rows = db.get_modules_summary()

    if not type_rows:
        st.info("暂无数据。请先初始化知识库。")
        return

    # 按模块汇总用于图表
    from collections import defaultdict
    mod_agg = defaultdict(lambda: {'total_q': 0, 'correct_q': 0, 'total_time': 0.0})
    for r in type_rows:
        mod = r['module']
        mod_agg[mod]['total_q'] += r['total_q'] or 0
        mod_agg[mod]['correct_q'] += r['correct_q'] or 0
        mod_agg[mod]['total_time'] += r['total_time'] or 0.0

    mod_names = sorted(mod_agg.keys())
    accuracies = [
        (mod_agg[m]['correct_q'] / mod_agg[m]['total_q'] * 100) if mod_agg[m]['total_q'] > 0 else 0
        for m in mod_names
    ]
    avg_times = [
        mod_agg[m]['total_time'] / mod_agg[m]['total_q'] if mod_agg[m]['total_q'] > 0 else 0
        for m in mod_names
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name='正确率 (%)', x=mod_names, y=accuracies,
        marker_color='#1a73e8', yaxis='y',
    ))
    fig.add_trace(go.Scatter(
        name='平均用时 (秒)', x=mod_names, y=avg_times,
        marker_color='#e53935', yaxis='y2', mode='lines+markers',
    ))
    fig.update_layout(
        title='各模块正确率与平均用时',
        yaxis=dict(title='正确率 (%)', range=[0, 100]),
        yaxis2=dict(title='平均用时 (秒)', overlaying='y', side='right'),
        height=350, margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 按模块展示题型分解
    st.markdown("### 模块 × 题型 明细")
    type_by_module = defaultdict(list)
    for r in type_rows:
        type_by_module[r['module']].append(r)

    for mod in mod_names:
        items = type_by_module[mod]
        first_qt = items[0].get('question_type', '') if items else ''
        if len(items) <= 1 and first_qt in ('', mod):
            # 没有细分的模块，简单展示
            m = items[0]
            st.markdown(
                f"**{mod}** — {m['total_q']}题 | "
                f"正确率 {m['accuracy']:.1%} | "
                f"平均 {m['avg_time']:.1f}秒 | "
                f"{m['point_count']}个知识点"
            )
        else:
            with st.expander(f"**{mod}** — 共 {sum(it['total_q'] or 0 for it in items)} 题", expanded=True):
                for it in sorted(items, key=lambda x: -(x['total_q'] or 0)):
                    qt = it.get('question_type', '') or mod
                    acc = it['accuracy']
                    st.markdown(
                        f"- **{qt}**：{it['total_q']}题 | "
                        f"正确率 {acc:.1%} | "
                        f"平均 {it['avg_time']:.1f}秒 | "
                        f"{it['point_count']}个知识点"
                    )


def _render_weak_points(db: KnowledgeDB):
    """渲染薄弱知识点排行榜。"""
    sort_by = st.radio("排序方式", ["按正确率", "按错误次数"], horizontal=True)
    order_by = 'accuracy' if sort_by == "按正确率" else 'error_count'

    weak = db.get_weak_points(limit=15, order_by=order_by)

    if not weak:
        st.info("暂无数据。")
        return

    # 柱状图
    labels = [w['full_label'][:20] for w in weak]
    errors = [w['error_count'] for w in weak]
    totals = [w['total_occurrences'] for w in weak]
    corrects = [w['correct_count'] for w in weak]

    fig = go.Figure()
    fig.add_trace(go.Bar(name='正确', x=labels, y=corrects, marker_color='#4caf50'))
    fig.add_trace(go.Bar(name='错误', x=labels, y=errors, marker_color='#e53935'))
    fig.update_layout(
        title='薄弱知识点 Top 15',
        barmode='stack',
        height=400,
        margin=dict(l=20, r=20, t=40, b=100),
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 表格
    st.markdown("### 详细数据")
    df_data = []
    for i, w in enumerate(weak, 1):
        df_data.append({
            '排名': i,
            '模块': w['module'],
            '题型': w.get('question_type') or w['module'],
            '知识点': w['point_name'],
            '错误/总数': f"{w['error_count']}/{w['total_occurrences']}",
            '正确率': f"{w['accuracy']:.1%}",
        })
    st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)

    # 知识点详情（点击查看跨考表现）
    st.markdown("---")
    st.markdown("### 🔍 知识点详情")
    selected_kp = st.selectbox(
        "选择知识点查看跨考表现",
        [w['point_name'] for w in weak],
        key="kp_detail_select"
    )
    if selected_kp:
        details = db.get_kp_cross_exam_detail(selected_kp)
        if details:
            correct_count = sum(1 for d in details if d['is_correct'])
            total_count = len(details)
            exams_involved = len(set(d['exam_name'] for d in details))
            st.markdown(
                f"**{selected_kp}**：{exams_involved} 场考试中出现 {total_count} 次，"
                f"正确 {correct_count} 次（{correct_count/max(total_count,1):.0%}）"
            )
            # 时间线
            dates = []
            results = []
            for d in details:
                exam_short = f"{d['exam_date']} {d['exam_name'][:15]}"
                dates.append(exam_short)
                results.append(1 if d['is_correct'] else 0)

            if len(dates) > 1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=dates, y=results,
                    mode='lines+markers',
                    marker=dict(size=12, color=['#4caf50' if r else '#e53935' for r in results]),
                    line=dict(color='#999', dash='dot'),
                ))
                fig.update_layout(
                    title=f'{selected_kp} 跨考表现',
                    yaxis=dict(tickvals=[0, 1], ticktext=['❌ 错误', '✅ 正确'], range=[-0.3, 1.3]),
                    height=250, margin=dict(l=20, r=20, t=40, b=80),
                )
                fig.update_xaxes(tickangle=-30)
                st.plotly_chart(fig, use_container_width=True)

            for d in details:
                icon = '✅' if d['is_correct'] else '❌'
                st.caption(
                    f"{icon} {d['exam_date']} | {d['source']} | "
                    f"你的：{_index_to_letter(d.get('your_answer'))} → "
                    f"正确：{_index_to_letter(d.get('correct_answer'))} | "
                    f"用时：{d.get('time_spent_sec', '-')}秒 | "
                    f"全站：{(d.get('global_correct_ratio', 0) or 0) * 100:.1f}%"
                )
        else:
            st.caption("暂无跨考数据")


def _render_trend_analysis(db: KnowledgeDB):
    """渲染历史趋势分析 + 考试对比。"""
    # ── 两场考试对比 ──
    exams = db.get_exam_records()
    if len(exams) >= 2:
        st.markdown("### 📊 两场考试对比")
        exam_names = [f"{e['exam_date']} {e['exam_name'][:20]}" for e in exams]
        col_a, col_b = st.columns(2)
        with col_a:
            idx1 = st.selectbox("考试 A", range(len(exam_names)), format_func=lambda i: exam_names[i], key="cmp_a")
        with col_b:
            idx2 = st.selectbox("考试 B", range(len(exam_names)), format_func=lambda i: exam_names[i],
                                index=min(1, len(exam_names)-1), key="cmp_b")
        if idx1 != idx2:
            e1, e2 = exams[idx1], exams[idx2]
            from collections import defaultdict
            import json as _j, os as _os
            def _mod_acc(rp):
                if not _os.path.exists(rp): return {}
                with open(rp, 'r', encoding='utf-8') as f:
                    data = _j.load(f)
                qs = data if isinstance(data, list) else data.get('questions',[])
                mods = defaultdict(lambda: [0,0])
                for q in qs:
                    if not isinstance(q, dict): continue
                    kps = q.get('keypoints',[])
                    names = [k.get('name','') for k in kps]
                    if not names: continue
                    from utils.analysis import classify_module
                    mm = classify_module(list(set(names)))
                    mod = next(iter(mm.keys()), '其他') if mm else '其他'
                    mods[mod][0] += 1
                    if q.get('status') == 1: mods[mod][1] += 1
                return {m: c1/max(c0,1) for m,(c0,c1) in mods.items() if c0>0}

            acc1, acc2 = _mod_acc(e1['report_path']), _mod_acc(e2['report_path'])
            all_mods = sorted(set(list(acc1.keys()) + list(acc2.keys())))
            if all_mods:
                rows = []
                for mod in all_mods:
                    a1, a2 = acc1.get(mod, 0), acc2.get(mod, 0)
                    delta = a2 - a1
                    icon = '📈' if delta > 0.03 else ('📉' if delta < -0.03 else '➡️')
                    rows.append({'模块': mod, f'{e1["exam_name"][:10]}': f'{a1:.0%}',
                                 f'{e2["exam_name"][:10]}': f'{a2:.0%}', '变化': f'{icon} {delta:+.0%}'})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── 趋势分析 ──
    all_points = db.get_all_knowledge_points()

    if not all_points:
        st.info("暂无数据。")
        return

    # 知识点选择
    point_options = {kp['full_label']: kp for kp in all_points
                     if kp['total_occurrences'] >= 2}
    if not point_options:
        st.info("需要有至少出现2次的知识点才能分析趋势。")
        return

    selected_label = st.selectbox(
        "选择知识点查看趋势",
        list(point_options.keys())
    )

    if selected_label:
        kp = point_options[selected_label]
        trend = json.loads(kp.get('trend_data', '[]'))

        if trend:
            # 趋势折线图
            sessions = list(range(1, len(trend) + 1))
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=sessions,
                y=[v * 100 for v in trend],
                mode='lines+markers',
                name='正确/错误',
                line=dict(color='#1a73e8', width=2),
                marker=dict(size=8),
            ))
            fig.add_hline(
                y=50, line_dash="dash", line_color="gray",
                annotation_text="50%"
            )
            fig.update_layout(
                title=f'{selected_label} 历次正确率趋势',
                xaxis_title='模考次数（从旧到新）',
                yaxis_title='结果（100=正确, 0=错误）',
                yaxis=dict(range=[-10, 110], tickvals=[0, 100], ticktext=['错误', '正确']),
                height=350,
                margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

            # 统计
            correct_rate = sum(trend) / len(trend)
            st.metric("该知识点整体正确率", f"{correct_rate:.1%}")
            if len(trend) >= 2:
                recent_rate = sum(trend[-3:]) / min(len(trend), 3)
                older_rate = sum(trend[:-3]) / max(len(trend) - 3, 1) if len(trend) > 3 else recent_rate
                delta = recent_rate - older_rate
                st.metric(
                    "最近3次 vs 之前",
                    f"{recent_rate:.1%}",
                    delta=f"{delta:+.1%}"
                )
        else:
            st.info("该知识点暂无趋势数据。")

    # 全站正确率偏离度
    st.markdown("---")
    st.markdown("### 全站正确率偏离度")
    st.caption("你的正确率 vs 全站考生正确率，差距越大越需关注")
    gaps = db.get_global_accuracy_gap(limit=20)
    if gaps:
        # 按模块→题型分组
        from collections import defaultdict
        gap_tree = defaultdict(lambda: defaultdict(list))
        for g in gaps:
            qt = g.get('question_type', '') or g['module']
            gap_tree[g['module']][qt].append(g)

        for mod in sorted(gap_tree.keys()):
            qt_data = gap_tree[mod]
            mod_gaps = [g for qt_list in qt_data.values() for g in qt_list]
            top_gap = max(mod_gaps, key=lambda g: g['gap'])
            with st.expander(
                f"**{mod}** — 最大偏离 {top_gap['gap']*100:.1f}%（{top_gap['point_name']}）",
                expanded=(top_gap['gap'] > 0.2)
            ):
                for qt in sorted(qt_data.keys()):
                    items = sorted(qt_data[qt], key=lambda g: -g['gap'])[:3]
                    for g in items:
                        st.markdown(
                            f"- {g['point_name']}：你的 {g['my_accuracy']:.0%} / "
                            f"全站 {g['avg_global_accuracy']:.0%} "
                            f"（差距 {g['gap']*100:.1f}%）"
                        )
    else:
        st.info("暂无足够的全站正确率数据。")


def _render_error_distribution(db: KnowledgeDB):
    """渲染错误类型分布——按模块展开到题型粒度。"""
    by_module = db.get_error_type_by_module()

    if not by_module:
        st.info("暂无错误诊断数据。请先对错题运行 AI 诊断并确认。")
        return

    # 过滤「其他」
    effective = [r for r in by_module if r['error_type'] != '其他']
    other_total = sum(r['count'] for r in by_module if r['error_type'] == '其他')
    total = sum(r['count'] for r in by_module)

    if not effective:
        st.info("所有错误类型均为「其他」，请到错题列表运行 AI 诊断并确认。")
        return

    # 按模块分组
    from collections import defaultdict
    mod_data = defaultdict(lambda: defaultdict(int))
    for r in effective:
        mod_data[r['module']][r['error_type']] += r['count']

    # 全局饼图
    global_dist = defaultdict(int)
    for r in effective:
        global_dist[r['error_type']] += r['count']

    fig = px.pie(
        names=list(global_dist.keys()), values=list(global_dist.values()),
        title=f'全局错误类型分布（共 {total} 次，已排除「其他」{other_total} 次）',
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # 按模块展开
    st.markdown("### 📊 各模块错误类型")
    for mod in sorted(mod_data.keys()):
        dist = mod_data[mod]
        mod_total = sum(dist.values())
        if mod_total < 3:
            continue  # 样本太少跳过
        with st.expander(f"**{mod}**（{mod_total} 次错误）", expanded=(mod_total >= 10)):
            # 按题型细分
            qt_data = defaultdict(lambda: defaultdict(int))
            for r in effective:
                if r['module'] == mod:
                    qt_data[r['question_type']][r['error_type']] += r['count']

            for qt, qt_dist in sorted(qt_data.items()):
                qt_total = sum(qt_dist.values())
                sorted_types = sorted(qt_dist.items(), key=lambda x: -x[1])
                type_str = ' | '.join(f"{et}×{c}" for et, c in sorted_types[:4])
                st.markdown(f"- **{qt}**（{qt_total}次）：{type_str}")

    all_points = db.get_all_knowledge_points()
    matrix_data = {'easy': [], 'medium': [], 'hard': []}
    for kp in all_points:
        diff_dist = json.loads(kp.get('difficulty_distribution', '{}'))
        total = kp['total_occurrences']
        correct = kp['correct_count']
        accuracy = correct / max(total, 1)
        for diff in ['easy', 'medium', 'hard']:
            if diff_dist.get(diff, 0) > 0:
                matrix_data[diff].append(accuracy)

    if any(matrix_data.values()):
        fig = go.Figure()
        for diff, accs in matrix_data.items():
            if accs:
                fig.add_trace(go.Box(
                    y=accs, name=diff,
                    marker_color={'easy': '#4caf50', 'medium': '#ff9800', 'hard': '#e53935'}[diff],
                ))
        fig.update_layout(
            title='不同难度级别的正确率分布',
            yaxis_title='正确率',
            height=350,
        )
        st.plotly_chart(fig, use_container_width=True)

    # 用时异常知识点
    st.markdown("---")
    st.markdown("### ⏰ 用时异常知识点 Top 5")
    time_anomaly = db.get_time_anomaly_points(limit=5)
    if time_anomaly:
        for i, ta in enumerate(time_anomaly, 1):
            st.metric(
                f"{i}. {ta['full_label']}",
                f"平均 {ta['avg_time']:.1f} 秒/题",
                f"偏离度 {ta['deviation_ratio']:.2f}x",
            )


# ======================== 右栏：AI 聊天 ========================

def render_right_panel(db: KnowledgeDB):
    """渲染 AI 顾问。"""
    # 聊天气泡 CSS
    st.markdown("""
    <style>
    .chat-row { display: flex; margin: 0.5rem 0; }
    .chat-row.user { justify-content: flex-end; }
    .chat-bubble { max-width: 80%; padding: 0.6rem 1rem; border-radius: 1.2rem; font-size: 0.9rem; line-height: 1.5; }
    .chat-bubble.assistant { background: #f0f2f6; border-bottom-left-radius: 0.3rem; }
    .chat-bubble.user { background: #1a73e8; color: #fff; border-bottom-right-radius: 0.3rem; }
    </style>
    """, unsafe_allow_html=True)

    # 初始化聊天数据（多会话）
    if 'chat_data' not in st.session_state:
        st.session_state.chat_data = _load_chat_data()

    # 会话选择器
    data = st.session_state.chat_data
    convs = data.get('conversations', [])
    conv = _current_conv(data)
    conv_names = [c['name'] for c in convs]
    current_idx = conv_names.index(conv['name']) if conv['name'] in conv_names else 0

    col_c1, col_c2, col_c3 = st.columns([2.5, 1, 1])
    with col_c1:
        new_idx = st.selectbox("会话", range(len(convs)), format_func=lambda i: convs[i]['name'],
                               index=current_idx, key="conv_selector", label_visibility="collapsed")
        if new_idx != current_idx:
            for c in convs: c['active'] = False
            convs[new_idx]['active'] = True
            st.rerun()
    with col_c2:
        new_name = st.text_input("新建", key="new_conv_name", placeholder="会话名", label_visibility="collapsed")
        if new_name and st.button("+", key="add_conv"):
            import time as _t
            for c in convs: c['active'] = False
            convs.append({"id": f"conv_{int(_t.time())}", "name": new_name, "messages": [], "active": True})
            _save_chat_data(data)
            st.rerun()
    with col_c3:
        if len(convs) > 1 and st.button("🗑", key="del_conv"):
            convs.remove(conv)
            if convs: convs[-1]['active'] = True
            _save_chat_data(data)
            st.rerun()

    # ── AI 生成题组 ──
    with st.expander("🎯 AI 生成针对性题组", expanded=False):
        gen_module = st.selectbox("模块", ["政治理论","常识判断","言语理解与表达","数量关系","判断推理","资料分析"], key="gen_mod_ai")
        gen_count = st.slider("题量", 3, 10, 5, key="gen_count_ai")
        if st.button("生成题组（~¥0.01）", key="gen_practice_ai", disabled=not _llm_available()):
            with st.spinner("AI 出题中..."):
                from utils.llm import _get_client, _load_llm_config
                prompt = (
                    f"你是公考行测命题专家。生成{gen_count}道{gen_module}练习题。"
                    f"输出JSON数组：[{{'content':'题干','options':['A...','B...','C...','D...'],'answer':'0','explanation':'解析'}}]"
                    f"题干加解析不超过150字/题。"
                )
                try:
                    cfg = _load_llm_config()
                    client = _get_client()
                    resp = client.chat.completions.create(
                        model=cfg['model'], messages=[{'role':'user','content':prompt}],
                        max_tokens=1200, temperature=0.7,
                        response_format={'type':'json_object'},
                    )
                    import json as _j2
                    result = _j2.loads(resp.choices[0].message.content)
                    items = result if isinstance(result, list) else result.get('items', result.get('questions', []))
                    for qi, item in enumerate(items[:gen_count], 1):
                        with st.container(border=True):
                            st.markdown(f"**{qi}.** {item.get('content','')}")
                            for oi, opt in enumerate(item.get('options',[])[:4]):
                                st.caption(f"{chr(65+oi)}. {opt}")
                            with st.expander("查看答案"):
                                st.success(f"答案：{chr(65+int(item.get('answer','0')))} — {item.get('explanation','')}")
                except Exception as e:
                    st.error(f"生成失败：{e}")

    st.markdown("---")

    # 快捷提问
    with st.expander("💡 快捷提问", expanded=False):
        quick_questions = [
            "哪个模块最近下滑最严重？",
            "帮我制定本周薄弱点攻克计划",
            "分析我的主要错误类型及改进建议",
        ]
        cols = st.columns(3)
        for i, qq in enumerate(quick_questions):
            with cols[i]:
                if st.button(qq, key=f"quick_{i}", use_container_width=True):
                    _handle_chat(db, qq)

    # 聊天输入
    user_input = st.chat_input("输入你的问题...")
    if user_input:
        _handle_chat(db, user_input)

    # 气泡对话
    history = conv.get('messages', [])
    show_n = min(6, len(history))
    recent = history[-show_n:] if history else []
    old = history[:-show_n] if len(history) > show_n else []

    if old:
        with st.expander(f"📜 历史消息（{len(old)} 条）", expanded=False):
            for msg in old:
                role = msg['role']
                align = 'user' if role == 'user' else 'assistant'
                cls = 'user' if role == 'user' else 'assistant'
                st.markdown(
                    f'<div class="chat-row {align}"><div class="chat-bubble {cls}">{msg["content"]}</div></div>',
                    unsafe_allow_html=True
                )

    for msg in recent:
        role = msg['role']
        align = 'user' if role == 'user' else 'assistant'
        cls = 'user' if role == 'user' else 'assistant'
        st.markdown(
            f'<div class="chat-row {align}"><div class="chat-bubble {cls}">{msg["content"]}</div></div>',
            unsafe_allow_html=True
        )


def _handle_chat(db: KnowledgeDB, user_query: str):
    """处理一轮对话（存入当前会话）。"""
    data = st.session_state.get('chat_data', {'conversations': []})
    conv = _current_conv(data)

    # 添加用户消息
    conv['messages'].append({'role': 'user', 'content': user_query})

    # 获取知识库上下文
    db_context = db.get_db_context_for_chat()
    exam_ctx = st.session_state.get('current_exam_context', '')
    if exam_ctx:
        db_context = exam_ctx + '\n\n' + db_context

    # 构建对话历史
    conv_history = [
        {'role': m['role'], 'content': m['content']}
        for m in conv['messages'][:-1]
    ]

    # 调用 LLM
    with st.spinner("AI 思考中..."):
        response = chat_with_context(user_query, db_context, conv_history)

    # 添加 AI 回复
    conv['messages'].append({'role': 'assistant', 'content': response})

    # 持久化
    _save_chat_data(data)

    # 刷新
    st.rerun()


# ======================== 主入口 ========================

def main():
    """主函数：标签页布局。"""
    # 暗色模式
    if 'dark_mode' not in st.session_state:
        st.session_state['dark_mode'] = False

    with st.sidebar:
        st.markdown("### ⚙️ 设置")
        dark = st.toggle("🌙 暗色模式", value=st.session_state['dark_mode'])
        if dark != st.session_state['dark_mode']:
            st.session_state['dark_mode'] = dark
            st.rerun()

    dark_css = """
    <style>
        .stApp { background-color: #1a1a2e; color: #e0e0e0; }
        .st-expander { background-color: #16213e; }
        .st-bq { color: #e0e0e0; }
        .module-card { background: #16213e; }
    </style>
    """ if st.session_state['dark_mode'] else ""

    st.markdown(f"""
    <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
        <h2 style="color: #1a73e8; margin-bottom: 0;">📝 粉笔模考复盘助手</h2>
    </div>
    {dark_css}
    """, unsafe_allow_html=True)

    db = get_db()

    # ── 仪表盘 ──
    exams = db.get_exam_records()
    if exams:
        total_q = sum(e['total_questions'] or 0 for e in exams)
        total_c = sum(e['correct_questions'] or 0 for e in exams)
        total_time = sum(e['total_time_sec'] or 0 for e in exams)
        acc = total_c / max(total_q, 1)
        recent = sorted(exams, key=lambda e: e['exam_date'] or '')[-3:]
        delta_str = ''
        if len(recent) >= 2:
            ra = [e['correct_questions']/max(e['total_questions'],1) for e in recent if e['total_questions']]
            if len(ra) >= 2:
                delta = ra[-1] - ra[-2]
                delta_str = f" {'📈' if delta>0.02 else '📉' if delta<-0.02 else '➡️'}{delta:+.1%}"

        c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1.2, 1, 0.6, 0.6])
        c1.metric("📋 模考", len(exams))
        c2.metric("📝 题目", total_q)
        c3.metric("✅ 正确率", f"{acc:.1%}{delta_str}")
        c4.metric("⏱ 用时", f"{int(total_time//3600)}h{int(total_time%3600//60)}m")
        with c5:
            if st.button("📥 抓取", key="dash_fetch_btn", use_container_width=True):
                st.session_state['show_fetch'] = not st.session_state.get('show_fetch', False)
        with c6:
            import shutil as _su
            bpath = os.path.join(os.path.dirname(__file__), 'data', 'backup.zip')
            try:
                _su.make_archive(bpath[:-4], 'zip', os.path.join(os.path.dirname(__file__), 'data'), 'knowledge_base.db')
                with open(bpath, 'rb') as bf:
                    st.download_button("💾", bf, "kb_backup.zip", key="dash_bkup")
            except Exception:
                pass

    if st.session_state.get('show_fetch'):
        with st.container(border=True):
            col_a, col_b = st.columns([2, 1])
            with col_a:
                ei = st.text_input("URL 或 Exam Key", placeholder="https://spa.fenbi.com/...", key="dfk")
            with col_b:
                ci = st.text_input("Cookie（可选）", type="password", key="dck")
            if st.button("🚀 开始抓取并入库", key="dfb", disabled=not ei):
                from fetch import fetch_and_analyze
                r = fetch_and_analyze(ei, ci)
                if r['success']:
                    st.success(f"✅ {r['exam_name'][:30]} — {r['total_q']}题，正确{r['correct_q']}题")
                    st.session_state['show_fetch'] = False
                else:
                    st.error(r.get('error', '抓取失败'))

    # ── 标签页主区域 ──
    tabs = st.tabs([
        "📋 复盘报告", "📊 知识洞察", "📖 错题本",
        "🤖 AI 顾问", "📝 笔记链接"
    ])

    with tabs[0]:
        render_left_panel(db)
    with tabs[1]:
        render_middle_panel(db)
    with tabs[2]:
        # 错题本：默认使用最近一份报告
        last_rp = exams[0]['report_path'] if exams else ''
        _render_wrong_q_bank(db, last_rp)
    with tabs[3]:
        render_right_panel(db)
    with tabs[4]:
        _render_notes(db)
        st.markdown("---")
        _render_links(db)


if __name__ == '__main__':
    main()
