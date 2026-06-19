"""申论相关 API"""

import json, os
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db import get_db

router = APIRouter(tags=["shenlun"])


@router.post("/shenlun/fetch")
def fetch_shenlun(body: dict, db=Depends(get_db)):
    """抓取申论真题"""
    from fetch import fetch_shenlun_data
    return fetch_shenlun_data(
        body.get("exam_input", ""),
        paper_id=body.get("paper_id", ""),
        check_id=body.get("check_id", ""),
    )


@router.get("/shenlun/exams")
def list_shenlun_exams(db=Depends(get_db)):
    """申论试卷列表"""
    try:
        cur = db.conn.cursor()
        cur.execute("SELECT id, exam_name, exam_date FROM shenlun_exams ORDER BY exam_date DESC")
        return [{"id": r[0], "name": r[1], "date": r[2]} for r in cur.fetchall()]
    except:
        return []


@router.get("/shenlun/exams/{exam_id}")
def get_shenlun_exam(exam_id: int, db=Depends(get_db)):
    """申论试卷详情（题目+材料）"""
    cur = db.conn.cursor()
    cur.execute("SELECT * FROM shenlun_questions WHERE exam_id=? ORDER BY sort_order", (exam_id,))
    qs = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM shenlun_materials WHERE exam_id=? ORDER BY sort_order", (exam_id,))
    mats = [dict(r) for r in cur.fetchall()]

    # 补全材料关联
    for q in qs:
        idxs = q.get("material_indexes", "")
        q["_material_idxs"] = json.loads(idxs) if idxs else []

    return {"questions": qs, "materials": mats}


class SaveAnswer(BaseModel):
    question_id: int
    answer_text: str


@router.post("/shenlun/answers")
def save_answer(body: SaveAnswer, db=Depends(get_db)):
    """保存作答"""
    db.conn.execute(
        "INSERT INTO shenlun_answers (question_id, answer_text) VALUES (?, ?)",
        (body.question_id, body.answer_text),
    )
    db.conn.commit()
    return {"ok": True}


@router.get("/shenlun/answers/{question_id}")
def get_answers(question_id: int, db=Depends(get_db)):
    """获取某题的所有答案记录"""
    cur = db.conn.cursor()
    cur.execute("SELECT * FROM shenlun_answers WHERE question_id=? ORDER BY created_at DESC", (question_id,))
    return [dict(r) for r in cur.fetchall()]


class EvaluateBody(BaseModel):
    question_id: int
    question: str = ""
    answer: str = ""
    materials: str = ""
    question_type: str = ""
    score: str = ""
    word_limit: str = ""


@router.post("/shenlun/evaluate")
def evaluate(body: EvaluateBody):
    """AI 批改申论答案"""
    from utils.llm import evaluate_shenlun_answer
    return evaluate_shenlun_answer(
        question=body.question, answer=body.answer,
        materials=body.materials, question_type=body.question_type,
        score=body.score, word_limit=body.word_limit,
    )


@router.get("/shenlun/phrases")
def list_phrases(category: str = "全部", db=Depends(get_db)):
    """素材库"""
    try:
        cur = db.conn.cursor()
        if category == "全部":
            cur.execute("SELECT * FROM shenlun_phrases ORDER BY id DESC LIMIT 30")
        else:
            cur.execute("SELECT * FROM shenlun_phrases WHERE category=? ORDER BY id DESC LIMIT 30", (category,))
        return [dict(r) for r in cur.fetchall()]
    except:
        return []


@router.post("/shenlun/phrases")
def save_phrase(body: dict, db=Depends(get_db)):
    """收藏素材"""
    db.conn.execute(
        "INSERT INTO shenlun_phrases (content, tag, category) VALUES (?, ?, ?)",
        (body.get("content", ""), body.get("tag", ""), body.get("category", "金句")),
    )
    db.conn.commit()
    return {"ok": True}
