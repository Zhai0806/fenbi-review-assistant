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


def _load_chat_history() -> list[dict]:
    """从文件加载聊天记录。"""
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_chat_history(messages: list[dict]):
    """持久化聊天记录到文件。"""
    os.makedirs(os.path.dirname(CHAT_HISTORY_FILE), exist_ok=True)
    with open(CHAT_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


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
    if labeled >= len(wrong_qs) * 0.5:  # 半数以上已标注
        _render_learning_advice(wrong_qs, db)

    # ── 手动微调列表 ──
    st.markdown("---")
    st.caption("已标注的错题，可手动修改")
    for i, q in enumerate(wrong_qs, 1):
        current_type = q.get('error_type') or '其他'
        with st.expander(
            f"{i}. {_question_label(q, compact=True, index=i)} | "
            f"你的：{_index_to_letter(q.get('your_answer'))} → "
            f"正确：{_index_to_letter(q.get('correct_answer'))} | "
            f"{current_type}",
            expanded=False
        ):
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


def _render_trend_analysis(db: KnowledgeDB):
    """渲染历史趋势分析。"""
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
    """渲染右栏：AI 聊天。"""
    st.markdown('<div class="main-header">🤖 AI 备考顾问</div>', unsafe_allow_html=True)

    # 初始化聊天历史
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = _load_chat_history()

    # 快捷提问
    with st.expander("💡 快捷提问", expanded=False):
        quick_questions = [
            "哪个模块最近下滑最严重？",
            "帮我制定本周薄弱点攻克计划",
            "分析我的主要错误类型及改进建议",
            "我的资料分析水平如何？有什么提升建议？",
        ]
        cols = st.columns(2)
        for i, qq in enumerate(quick_questions):
            with cols[i % 2]:
                if st.button(qq, key=f"quick_{i}", use_container_width=True):
                    _handle_chat(db, qq)

    # 聊天输入
    user_input = st.chat_input("输入你的问题...")
    if user_input:
        _handle_chat(db, user_input)

    # 分隔历史与当前
    history = st.session_state.chat_history
    if len(history) > 8:
        # 折叠旧对话
        old_count = len(history) - 6
        with st.expander(f"📜 历史对话（{old_count} 条消息）", expanded=False):
            for msg in history[:old_count]:
                with st.chat_message(msg['role']):
                    st.markdown(msg['content'])
        # 显示最近 6 条
        for msg in history[old_count:]:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])
    else:
        for msg in history:
            with st.chat_message(msg['role']):
                st.markdown(msg['content'])


def _handle_chat(db: KnowledgeDB, user_query: str):
    """处理一轮对话。"""
    # 添加用户消息
    st.session_state.chat_history.append({
        'role': 'user',
        'content': user_query,
    })

    # 获取知识库上下文
    db_context = db.get_db_context_for_chat()

    # 构建对话历史
    conv_history = [
        {'role': m['role'], 'content': m['content']}
        for m in st.session_state.chat_history[:-1]  # 不包括刚添加的
    ]

    # 调用 LLM
    with st.spinner("AI 思考中..."):
        response = chat_with_context(user_query, db_context, conv_history)

    # 添加 AI 回复
    st.session_state.chat_history.append({
        'role': 'assistant',
        'content': response,
    })

    # 持久化保存
    _save_chat_history(st.session_state.chat_history)

    # 刷新界面
    st.rerun()


# ======================== 主入口 ========================

def main():
    """主函数：三栏布局。"""
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0 2rem 0;">
        <h1 style="color: #1a73e8; margin-bottom: 0;">📝 粉笔模考复盘助手</h1>
        <p style="color: #888; font-size: 0.9rem;">基于认知科学的行测/公基模考数据分析工具</p>
    </div>
    """, unsafe_allow_html=True)

    # 初始化数据库
    db = get_db()

    # 三栏布局
    left, middle, right = st.columns([1, 1.2, 0.8], gap="medium")

    with left:
        render_left_panel(db)

    with middle:
        render_middle_panel(db)

    with right:
        render_right_panel(db)


if __name__ == '__main__':
    main()
