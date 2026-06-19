"""AI 诊断相关 API"""

import os
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.db import get_db

router = APIRouter(tags=["diagnose"])


class ConfirmBody(BaseModel):
    error_type: str | None = None


@router.post("/diagnose/{exam_id}")
async def run_diagnose(exam_id: int, db=Depends(get_db)):
    """触发 AI 批量诊断（SSE 流式返回进度）"""
    exams = db.get_exam_records()
    exam = next((e for e in exams if e["id"] == exam_id), None)
    if not exam:
        return {"error": "exam not found"}

    from utils.analysis import diagnose_report_errors

    async def event_stream():
        yield f"data: {json.dumps({'status': 'started', 'msg': '开始诊断...'})}\n\n"
        try:
            result = diagnose_report_errors(db, exam["report_path"])
            yield f"data: {json.dumps({'status': 'done', **result})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'msg': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/diagnoses")
def list_diagnoses(exam_id: int | None = None, db=Depends(get_db)):
    """获取待确认的诊断列表"""
    exams = db.get_exam_records()
    exam = next((e for e in exams if e["id"] == exam_id), None) if exam_id else None
    rp = exam["report_path"] if exam else None
    pending = db.get_pending_diagnoses(rp)
    result = []
    for p in pending:
        qa = db.get_question_by_key(p["question_key"])
        result.append(
            {
                "id": p["id"],
                "question_key": p["question_key"],
                "error_type": p["error_type"],
                "confidence": p["confidence"],
                "specific_error": p.get("specific_error", ""),
                "explanation": p["explanation"],
                "source": qa.get("source", "") if qa else "",
                "your_answer": qa.get("your_answer", "") if qa else "",
                "correct_answer": qa.get("correct_answer", "") if qa else "",
            }
        )
    return result


@router.post("/diagnoses/{diag_id}/confirm")
def confirm_diagnosis(diag_id: int, body: ConfirmBody, db=Depends(get_db)):
    """确认诊断"""
    db.confirm_diagnosis(diag_id, final_error_type=body.error_type)
    return {"ok": True}
