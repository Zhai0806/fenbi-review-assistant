"""AI 对话 + 题组生成 API"""

import json, os, time
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.db import get_db

router = APIRouter(tags=["chat"])

CHAT_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chat_history.json")


def _load_chat_data() -> dict:
    if os.path.exists(CHAT_FILE):
        try:
            with open(CHAT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                data = {"conversations": [{"id": f"conv_{int(time.time())}", "name": "旧对话", "messages": data}]}
            return data
        except (json.JSONDecodeError, IOError):
            pass
    return {"conversations": []}


def _save_chat_data(data: dict):
    os.makedirs(os.path.dirname(CHAT_FILE), exist_ok=True)
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _current_conv(data: dict) -> dict:
    convs = data.get("conversations", [])
    if not convs:
        conv = {"id": f"conv_{int(time.time())}", "name": "行测复盘", "messages": [], "active": True}
        data["conversations"] = [conv]
        return conv
    active = next((c for c in convs if c.get("active")), None) or convs[-1]
    active["active"] = True
    return active


@router.get("/chat/conversations")
def list_conversations():
    data = _load_chat_data()
    convs = data.get("conversations", [])
    return [{"id": c["id"], "name": c["name"], "active": c.get("active", False), "msg_count": len(c.get("messages", []))} for c in convs]


@router.post("/chat/conversations")
def create_conversation(body: dict = {}):
    data = _load_chat_data()
    for c in data.get("conversations", []):
        c["active"] = False
    conv = {"id": f"conv_{int(time.time())}", "name": body.get("name", "新对话"), "messages": [], "active": True}
    data.setdefault("conversations", []).append(conv)
    _save_chat_data(data)
    return conv


@router.delete("/chat/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    data = _load_chat_data()
    data["conversations"] = [c for c in data.get("conversations", []) if c["id"] != conv_id]
    if data["conversations"]:
        data["conversations"][-1]["active"] = True
    _save_chat_data(data)
    return {"ok": True}


@router.post("/chat/conversations/{conv_id}/activate")
def activate_conversation(conv_id: str):
    data = _load_chat_data()
    for c in data.get("conversations", []):
        c["active"] = c["id"] == conv_id
    _save_chat_data(data)
    return {"ok": True}


class ChatMsg(BaseModel):
    query: str


@router.post("/chat/send")
def send_message(body: ChatMsg, db=Depends(get_db)):
    """发送消息，返回 AI 回复"""
    from utils.llm import chat_with_context
    import datetime as _dt

    data = _load_chat_data()
    conv = _current_conv(data)
    conv["messages"].append({"role": "user", "content": body.query})

    db_ctx = db.get_db_context_for_chat()
    today = _dt.date.today().isoformat()
    sys_prompt = f"你是公考备考顾问。今天 {today}。请基于考生数据提供建议。"
    db_ctx = f"【考生数据】\n{db_ctx}"

    try:
        response = chat_with_context(body.query, db_ctx, conv["messages"][:-1])
    except Exception as e:
        response = f"AI 暂时不可用：{e}"

    conv["messages"].append({"role": "assistant", "content": response})
    _save_chat_data(data)
    return {"reply": response, "messages": conv["messages"]}


class PracticeBody(BaseModel):
    module: str = "言语理解与表达"
    count: int = 5


@router.post("/practice/generate")
def generate_practice(body: PracticeBody):
    """AI 生成题组"""
    from utils.llm import _get_client, _load_llm_config

    prompt = (
        f"你是公考行测命题专家。生成{body.count}道{body.module}练习题。"
        f"输出JSON：{{\"items\":[{{\"content\":\"题干\",\"options\":[\"A\",\"B\",\"C\",\"D\"],\"answer\":\"0\",\"explanation\":\"解析\"}}]}}"
        f"题干加解析不超过150字/题。"
    )

    try:
        cfg = _load_llm_config()
        client = _get_client()
        resp = client.chat.completions.create(
            model=cfg["model"], messages=[{"role": "user", "content": prompt}],
            max_tokens=1200, temperature=0.7, response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        items = result if isinstance(result, list) else result.get("items", [])
        return {"questions": items[:body.count]}
    except Exception as e:
        return {"error": str(e)}
