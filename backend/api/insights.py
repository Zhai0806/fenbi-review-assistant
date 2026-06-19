"""知识洞察 API —— 模块分析/错误分布/偏离度/趋势/对比/KP详情"""

import os, json, re
from fastapi import APIRouter, Depends, Query

from backend.db import get_db

router = APIRouter(tags=["insights"])


@router.get("/insights/error-distribution")
def error_distribution(db=Depends(get_db)):
    """错误类型分布（按模块→题型）"""
    return db.get_error_type_by_module()


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
    """两场考试各模块正确率对比"""
    exams = db.get_exam_records()
    e1 = next((e for e in exams if e["id"] == a), None)
    e2 = next((e for e in exams if e["id"] == b), None)
    if not e1 or not e2:
        return {"error": "exam not found"}

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
    """矛盾分析：找出拖累全局的主要短板"""
    import json as _j, os as _os
    from collections import defaultdict

    exams = db.get_exam_records()
    mod_accuracy_per_exam = []  # [{exam_name, 模块: accuracy}]

    for exam in exams:
        rp = exam["report_path"]
        if not _os.path.exists(rp): continue
        qs = db.get_questions_by_report(rp)
        with open(rp, "r", encoding="utf-8") as f:
            data = _j.load(f)
        raw_qs = data if isinstance(data, list) else data.get("questions", [])
        q_map = {q.get("key", ""): q for q in raw_qs if isinstance(q, dict)}

        mod_counts = defaultdict(lambda: [0, 0])
        for qa in qs:
            rq = q_map.get(qa["question_key"], {})
            kps = rq.get("keypoints", [])
            names = [k.get("name", "") for k in kps]
            from utils.analysis import classify_module
            mm = classify_module(list(set(names))) if names else {}
            mod = next(iter(mm.keys()), "其他") if mm else "其他"
            mod_counts[mod][0] += 1
            if qa.get("is_correct"): mod_counts[mod][1] += 1

        entry = {"name": (exam["exam_name"] or "")[:20], "date": exam["exam_date"]}
        for mod, (t, c) in mod_counts.items():
            if t >= 3: entry[mod] = round(c / t * 100, 1)
        mod_accuracy_per_exam.append(entry)

    if len(mod_accuracy_per_exam) < 2:
        return {"principal": "", "analysis": [], "advice": "需要≥2场考试才能分析"}

    # 找出整体正确率最低的模块（主要矛盾）
    all_mods = set()
    for m in mod_accuracy_per_exam: all_mods.update(k for k in m if k not in ("name", "date"))

    mod_avg = {}
    for mod in all_mods:
        vals = [m[mod] for m in mod_accuracy_per_exam if mod in m]
        if vals: mod_avg[mod] = round(sum(vals) / len(vals), 1)

    sorted_mods = sorted(mod_avg.items(), key=lambda x: x[1])
    principal = sorted_mods[0][0] if sorted_mods else ""

    # 分析连锁影响：哪个模块拖累全局最严重
    analysis = []
    for mod, avg in sorted_mods[:4]:
        # 计算该模块与总分的相关性
        others_avg = sorted([(m, a) for m, a in sorted_mods if m != mod], key=lambda x: x[1])
        improvement = others_avg[0][1] - avg if others_avg else 0
        analysis.append({
            "module": mod, "accuracy": avg,
            "gap": round(improvement, 1),
            "advice": f"该模块正确率{avg}%，与最强模块差距{round(improvement, 1)}个百分点。" + (
                "该模块的基础能力可能影响其他模块表现，优先攻克。" if avg < 50 else
                "该模块有较大提升空间，建议针对性训练。" if avg < 65 else
                "该模块表现接近平均水平，保持即可。" if avg < 75 else
                "该模块表现正常。"
            ) if improvement > 5 else "各模块表现均衡，继续保持。"
        })

    return {
        "principal": principal,
        "analysis": analysis,
        "advice": f"主要矛盾在「{principal}」，攻克它可能带来最大的整体提升。"
    }


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
