"""题目相关 API"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from backend.db import get_db

router = APIRouter(tags=["questions"])


class UpdateQuestion(BaseModel):
    user_note: str | None = None


@router.put("/questions/{question_key}")
def update_question(question_key: str, body: UpdateQuestion, db=Depends(get_db)):
    """更新单题的备注"""
    if body.user_note is not None:
        db.update_question_field(question_key, "user_note", body.user_note)
    return {"ok": True}


@router.get("/questions/{question_key}/raw")
def get_question_raw(question_key: str, db=Depends(get_db)):
    """获取题目的原始内容（题干+选项+知识点，用于显示）"""
    import json
    import os
    import re

    exams = db.get_exam_records()
    for exam in exams:
        rp = exam["report_path"]
        if not os.path.exists(rp):
            continue
        with open(rp, "r", encoding="utf-8") as f:
            data = json.load(f)
        qs = data if isinstance(data, list) else data.get("questions", [])
        for q in qs:
            if not isinstance(q, dict):
                continue
            if q.get("key", "") == question_key:
                return {
                    "key": q.get("key"),
                    "content": q.get("content", ""),
                    "options": q.get("options", []),
                    "solution": q.get("solution", ""),
                    "keypoints": q.get("keypoints", []),
                    "source": q.get("source", ""),
                    "materialKeys": q.get("materialKeys", []),
                }
    return {"error": "not found"}


@router.get("/modules/summary")
def modules_summary(db=Depends(get_db)):
    """模块概览（含题型分组）"""
    return db.get_modules_summary()


@router.get("/wrong-bank")
def wrong_bank(
    module: str = Query("全部"),
    count: int = Query(10),
    shuffle: bool = Query(True),
    db=Depends(get_db),
):
    """错题本：跨考聚合错题，支持模块筛选、乱序"""
    import random, json as _j, os as _os

    all_wrong = []
    exams = db.get_exam_records()
    for exam in exams:
        rp = exam["report_path"]
        if not _os.path.exists(rp):
            continue
        with open(rp, "r", encoding="utf-8") as f:
            data = _j.load(f)
        qs = data if isinstance(data, list) else data.get("questions", [])
        for q in qs:
            if not isinstance(q, dict) or q.get("status") != -1:
                continue
            kps = q.get("keypoints", [])
            names = [k.get("name", "") for k in kps]
            from utils.analysis import classify_module
            mm = classify_module(list(set(names))) if names else {}
            mod = next(iter(mm.keys()), "其他") if mm else "其他"
            qa = db.get_question_by_key(q.get("key", ""))
            all_wrong.append({
                "key": q.get("key"), "source": q.get("source", ""),
                "content": q.get("content", ""), "options": q.get("options", []),
                "your_answer": qa.get("your_answer", "") if qa else q.get("your_answer", ""),
                "correct_answer": qa.get("correct_answer", "") if qa else q.get("correct_answer", ""),
                "module": mod,
                "time_sec": q.get("time_spent_sec", 0), "exam_name": exam["exam_name"],
                "exam_date": exam["exam_date"],
            })

    if module != "全部":
        all_wrong = [q for q in all_wrong if q["module"] == module]
    if shuffle:
        random.shuffle(all_wrong)
    return all_wrong[:count]


@router.get("/weak-points-by-type")
def weak_points_by_type(db=Depends(get_db)):
    """薄弱点按模块→题型聚合（废弃知识点体系）"""
    cur = db.conn.cursor()
    cur.execute("""
        SELECT module, question_type, SUM(total_occurrences) as total_q,
               SUM(correct_count) as correct_q
        FROM knowledge_points GROUP BY module, question_type
    """)
    result = []
    for r in cur.fetchall():
        total = r[2] or 0
        correct = r[3] or 0
        result.append({
            "module": r[0], "question_type": r[1] or r[0],
            "total": total, "correct": correct,
            "wrong": total - correct,
            "accuracy": correct / max(total, 1),
        })
    result.sort(key=lambda x: x["accuracy"])
    return result


@router.get("/weak-points")
def weak_points(
    order_by: str = Query("accuracy"),
    limit: int = Query(15),
    db=Depends(get_db),
):
    """薄弱知识点排行"""
    return db.get_weak_points(limit=limit, order_by=order_by)
