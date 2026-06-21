"""模考相关 API"""

import json, os
from fastapi import APIRouter, Depends

from backend.db import get_db

router = APIRouter(tags=["exams"])


@router.post("/exams/fetch")
def fetch_exam(body: dict, db=Depends(get_db)):
    """抓取 + 入库模考数据"""
    from fetch import fetch_and_analyze
    return fetch_and_analyze(body.get("input", ""), body.get("cookie", ""))


@router.get("/exams")
def list_exams(db=Depends(get_db)):
    """获取所有模考记录"""
    exams = db.get_exam_records()
    return [
        {
            "id": e["id"],
            "name": e["exam_name"],
            "date": e["exam_date"],
            "total": e["total_questions"],
            "correct": e["correct_questions"],
            "time_sec": e["total_time_sec"],
            "path": e["report_path"],
            "type": e.get("exam_type", "行测"),
        }
        for e in exams
    ]


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, db=Depends(get_db)):
    """获取单份模考详情"""
    exams = db.get_exam_records()
    exam = next((e for e in exams if e["id"] == exam_id), None)
    if not exam:
        return {"error": "not found"}

    questions = db.get_questions_by_report(exam["report_path"])

    # 按 source 中的题号排序（DB 存储顺序是模块分组，不是考试正序）
    import re as _re
    def _qnum(q):
        m = _re.search(r"第(\d+)题", q.get("source", "") or "")
        return int(m.group(1)) if m else 9999
    questions.sort(key=_qnum)

    # 加载材料
    materials = []
    try:
        with open(exam["report_path"], "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            mats = data.get("materials", [])
            materials = [{"id": m.get("id", 0), "globalId": m.get("globalId", ""), "content": m.get("content", "")} for m in mats if isinstance(m, dict)]
            # 注入 materialKeys + 模块分类（从 knowledge_points 查已分类的结果）
            q_list = data.get("questions", [])
            q_map = {q.get("key", ""): q for q in q_list if isinstance(q, dict)}
            # 预加载知识点→模块映射（DB已有，不再实时分类）
            cur = db.conn.cursor()
            cur.execute("SELECT point_name, module FROM knowledge_points")
            kp_to_mod = {r[0]: r[1] for r in cur.fetchall()}

            for qi, q in enumerate(questions):
                rq = q_map.get(q["question_key"], {})
                q["materialKeys"] = rq.get("materialKeys", [])
                q["raw_content"] = rq.get("content", "")
                opts = rq.get("options", [])
                if not opts:
                    acc = rq.get("accessories", [])
                    if acc and isinstance(acc[0], dict):
                        opts = acc[0].get("options", [])
                q["raw_options"] = opts
                # 从 DB 查模块（多数投票）
                kps = rq.get("keypoints", [])
                from collections import Counter as _Ct
                mod_votes = _Ct()
                for kp in kps:
                    name = kp.get("name", "") if isinstance(kp, dict) else str(kp)
                    m = kp_to_mod.get(name, "其他")
                    if m != "其他":
                        mod_votes[m] += 1
                q["module"] = mod_votes.most_common(1)[0][0] if mod_votes else "其他"
                q["index"] = qi + 1  # 现在 qi 是基于题号排序后的顺序
                q["status"] = rq.get("status", 0)
                q["_qnum"] = _qnum(q)  # 源题号
    except Exception:
        pass

    return {
        "id": exam["id"],
        "name": exam["exam_name"],
        "date": exam["exam_date"],
        "total": exam["total_questions"],
        "correct": exam["correct_questions"],
        "time_sec": exam["total_time_sec"],
        "accuracy": exam["correct_questions"] / max(exam["total_questions"], 1),
        "summary": exam.get("exam_summary", "") or "",
        "materials": materials,
        "questions": [
            {
                "key": q["question_key"],
                "source": q.get("source", ""),
                "your_answer": q.get("your_answer", ""),
                "correct_answer": q.get("correct_answer", ""),
                "is_correct": q.get("is_correct", False),
                "time_sec": q.get("time_spent_sec"),
                "global_ratio": q.get("global_correct_ratio") or 0,
                "is_guessed": q.get("is_guessed_correct", False),
                "is_time_anomaly": q.get("is_time_anomaly", False),
                "user_note": q.get("user_note", ""),
                "materialKeys": q.get("materialKeys", []),
                "raw_content": q.get("raw_content", ""),
                "raw_options": q.get("raw_options", []),
                "status": q.get("status", 0),
                "index": q.get("index", 0),
                "module": q.get("module", "其他"),
                "_qnum": q.get("_qnum", 0),
            }
            for q in questions
        ],
    }
