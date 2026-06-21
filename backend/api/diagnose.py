"""AI 诊断相关 API"""

import json
import asyncio
import threading
from queue import Queue, Empty
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.db import get_db

router = APIRouter(tags=["diagnose"])

# 诊断取消信号：{exam_id: threading.Event}
_cancel_events: dict[int, threading.Event] = {}


@router.post("/diagnose/{exam_id}")
async def run_diagnose(exam_id: int, db=Depends(get_db)):
    """触发 AI 批量诊断（SSE 流式返回进度）"""
    exams = db.get_exam_records()
    exam = next((e for e in exams if e["id"] == exam_id), None)
    if not exam:
        return {"error": "exam not found"}

    from utils.analysis import diagnose_report_errors

    # 创建取消信号
    cancel_evt = threading.Event()
    _cancel_events[exam_id] = cancel_evt

    async def event_stream():
        yield f"data: {json.dumps({'status': 'started', 'msg': '开始诊断... v3-errmsg'})}\n\n"

        q: Queue = Queue()
        error_holder: list = []

        def run_diagnosis():
            try:
                for event in diagnose_report_errors(db, exam["report_path"], cancel_event=cancel_evt):
                    q.put(event)
                q.put(None)  # sentinel: done
            except Exception as e:
                error_holder.append(e)
                q.put(None)

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run_diagnosis)

        while True:
            event = await loop.run_in_executor(None, q.get)
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

        if error_holder:
            yield f"data: {json.dumps({'status': 'error', 'msg': str(error_holder[0])})}\n\n"
        # 清理取消信号
        _cancel_events.pop(exam_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/diagnose/{exam_id}/cancel")
def cancel_diagnose(exam_id: int):
    """取消正在进行的诊断"""
    evt = _cancel_events.get(exam_id)
    if evt:
        evt.set()
        return {"ok": True, "msg": "已发送取消信号"}
    return {"ok": False, "msg": "没有正在进行的诊断"}


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
                "confidence": p["confidence"],
                "specific_error": p.get("specific_error", ""),
                "countermeasure": p.get("countermeasure", ""),
                "explanation": p["explanation"],
                "source": qa.get("source", "") if qa else "",
                "your_answer": qa.get("your_answer", "") if qa else "",
                "correct_answer": qa.get("correct_answer", "") if qa else "",
            }
        )
    return result


@router.post("/diagnoses/{diag_id}/confirm")
def confirm_diagnosis(diag_id: int, db=Depends(get_db)):
    """确认诊断"""
    db.confirm_diagnosis(diag_id)
    return {"ok": True}
