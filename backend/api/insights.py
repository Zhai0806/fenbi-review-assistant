"""知识洞察 API —— 模块分析/错误分布/偏离度/趋势/对比/KP详情"""

import os, json, re
from fastapi import APIRouter, Depends, Query

from backend.db import get_db

router = APIRouter(tags=["insights"])


@router.get("/insights/error-distribution")
def error_distribution(db=Depends(get_db)):
    """错误类型分布已废弃——返回空列表"""
    return []


@router.get("/insights/accuracy-gap")
def accuracy_gap(limit: int = Query(20), db=Depends(get_db)):
    """全站正确率偏离度"""
    return db.get_global_accuracy_gap(limit=limit)


@router.get("/insights/persistent-weak")
def persistent_weak(db=Depends(get_db)):
    """跨考持续薄弱知识点"""
    from utils.analysis import detect_persistent_weak_points
    return detect_persistent_weak_points(db, min_consecutive=2)


@router.get("/insights/exams-compare")
def exams_compare(a: int = Query(...), b: int = Query(...), db=Depends(get_db)):
    """两场考试各模块正确率对比（仅同类型可比较）"""
    exams = db.get_exam_records()
    e1 = next((e for e in exams if e["id"] == a), None)
    e2 = next((e for e in exams if e["id"] == b), None)
    if not e1 or not e2:
        return {"error": "exam not found"}

    # 禁止跨考试类型比较（公基 vs 行测 模块不同，没有可比性）
    t1 = e1.get("exam_type", "行测/职测")
    t2 = e2.get("exam_type", "行测/职测")
    if t1 != t2:
        return {"error": f"不能跨考试类型比较：{t1} vs {t2}，模块体系不同无意义"}

    from collections import defaultdict

    def mod_acc(rp):
        if not os.path.exists(rp):
            return {}
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
        qs = data if isinstance(data, list) else data.get("questions", [])
        mods = defaultdict(lambda: [0, 0])
        for q in qs:
            if not isinstance(q, dict):
                continue
            kps = q.get("keypoints", [])
            names = [k.get("name", "") for k in kps]
            if not names:
                continue
            from utils.analysis import classify_module
            mm = classify_module(list(set(names)))
            mod = next(iter(mm.keys()), "其他") if mm else "其他"
            mods[mod][0] += 1
            if q.get("status") == 1:
                mods[mod][1] += 1
        return {m: c1 / max(c0, 1) for m, (c0, c1) in mods.items() if c0 > 0}

    a1 = mod_acc(e1["report_path"])
    a2 = mod_acc(e2["report_path"])
    all_mods = sorted(set(list(a1.keys()) + list(a2.keys())))

    return {
        "exam_a": e1["exam_name"],
        "exam_b": e2["exam_name"],
        "type_a": t1,
        "type_b": t2,
        "modules": [
            {
                "module": m,
                "acc_a": a1.get(m, 0),
                "acc_b": a2.get(m, 0),
                "delta": a2.get(m, 0) - a1.get(m, 0),
            }
            for m in all_mods
        ],
    }


@router.get("/insights/kp-detail")
def kp_detail(name: str = Query(...), db=Depends(get_db)):
    """知识点跨考详情"""
    return db.get_kp_cross_exam_detail(name)


@router.get("/insights/contradiction")
def contradiction_analysis(db=Depends(get_db)):
    """矛盾分析——按考试类型独立缓存，诊断完成后已预生成，秒返。

    返回格式：{ "行测/职测": {...}, "公基": {...} }
    """
    from utils.analysis import generate_contradiction_analysis
    return generate_contradiction_analysis(db)


@router.get("/insights/exam-trend")
def exam_trend(db=Depends(get_db)):
    """各模块跨考正确率趋势"""
    exams = db.get_exam_records()
    exams_sorted = sorted(exams, key=lambda e: e["exam_date"] or "")

    trend = []
    for exam in exams_sorted:
        rp = exam["report_path"]
        if not os.path.exists(rp): continue
        qs = db.get_questions_by_report(rp)
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_qs = data if isinstance(data, list) else data.get("questions", [])
        q_map = {q.get("key", ""): q for q in raw_qs if isinstance(q, dict)}

        mod_acc: dict = {"date": exam["exam_date"] or "", "name": (exam["exam_name"] or "")[:12]}
        mod_counts: dict = {}
        for qa in qs:
            rq = q_map.get(qa["question_key"], {})
            kps = rq.get("keypoints", [])
            names = [k.get("name", "") for k in kps]
            from utils.analysis import classify_module
            mm = classify_module(list(set(names))) if names else {}
            mod = next(iter(mm.keys()), "其他") if mm else "其他"

            if mod not in mod_counts: mod_counts[mod] = [0, 0]
            mod_counts[mod][0] += 1
            if qa.get("is_correct"): mod_counts[mod][1] += 1

        for mod, (t, c) in mod_counts.items():
            if t >= 3:
                mod_acc[mod] = round(c / t * 100, 1)

        trend.append(mod_acc)

    # filter out empty entries
    trend = [t for t in trend if len(t) > 2]
    return trend


@router.get("/insights/module-timing")
def module_timing(exam_id: int = Query(...), db=Depends(get_db)):
    """某份模考的模块用时分析"""
    exams = db.get_exam_records()
    exam = next((e for e in exams if e["id"] == exam_id), None)
    if not exam:
        return {"error": "exam not found"}

    rp = exam["report_path"]
    if not os.path.exists(rp):
        return {"error": "report not found"}

    with open(rp, "r", encoding="utf-8") as f:
        data = json.load(f)
    qs = data if isinstance(data, list) else data.get("questions", [])

    from utils.analysis import analyze_module_timing
    return analyze_module_timing(qs)
