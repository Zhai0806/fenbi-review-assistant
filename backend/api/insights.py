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


@router.get("/insights/actionable-stats")
def actionable_stats(db=Depends(get_db)):
    """实用备考统计：送分题杀手 + 不该放弃的题 + 投入产出Top3"""
    import json as _j, os as _os
    from collections import defaultdict

    exams = db.get_exam_records()
    all_questions = []
    kp_stats = defaultdict(lambda: {"wrong": 0, "total": 0, "global_sum": 0.0, "global_count": 0})

    for exam in exams:
        rp = exam["report_path"]
        if not _os.path.exists(rp):
            continue
        qs = db.get_questions_by_report(rp)
        with open(rp, "r", encoding="utf-8") as f:
            data = _j.load(f)
        raw_qs = data if isinstance(data, list) else data.get("questions", [])
        q_map = {q.get("key", ""): q for q in raw_qs if isinstance(q, dict)}

        for qa in qs:
            qk = qa["question_key"]
            rq = q_map.get(qk, {})
            kps = rq.get("keypoints", [])
            kp_names = [k.get("name", "") for k in kps]
            time_sec = qa.get("time_spent_sec") or 0
            global_ratio = qa.get("global_correct_ratio") or 0
            is_correct = qa.get("is_correct", False)

            all_questions.append({
                "source": qa.get("source", ""), "is_correct": is_correct,
                "time_sec": time_sec, "global_ratio": global_ratio,
                "your_answer": qa.get("your_answer", ""),
                "correct_answer": qa.get("correct_answer", ""),
                "exam_name": exam["exam_name"], "kp_names": kp_names,
            })

            for kp in kp_names:
                kp_stats[kp]["total"] += 1
                kp_stats[kp]["global_sum"] += global_ratio
                kp_stats[kp]["global_count"] += 1
                if not is_correct:
                    kp_stats[kp]["wrong"] += 1

    # 1. 送分题杀手（全站>70%但你做错了）
    free_kills = [q for q in all_questions if not q["is_correct"] and q["global_ratio"] > 0.7]
    free_kills.sort(key=lambda q: -q["global_ratio"])

    # 2. 不该放弃的题（用时<10s + 全站>50% + 你做错了）
    should_not_give_up = [q for q in all_questions if not q["is_correct"] and q["time_sec"] < 10 and q["global_ratio"] > 0.5]
    should_not_give_up.sort(key=lambda q: -q["global_ratio"])

    # 3. 投入产出最高知识点 Top5（错得多 + 全站正确率高 = 容易补的短板）
    kp_roi = []
    for kp, s in kp_stats.items():
        if s["total"] >= 2 and s["wrong"] > 0:
            avg_global = s["global_sum"] / max(s["global_count"], 1)
            wrong_rate = s["wrong"] / max(s["total"], 1)
            roi = avg_global * wrong_rate  # 全站高 + 你错得多 = 该补
            kp_roi.append({"kp": kp, "wrong": s["wrong"], "total": s["total"],
                           "avg_global": avg_global, "roi": roi})
    kp_roi.sort(key=lambda x: -x["roi"])

    return {
        "free_kills": free_kills[:10],
        "should_not_give_up": should_not_give_up[:10],
        "top_roi_kps": kp_roi[:5],
    }


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
