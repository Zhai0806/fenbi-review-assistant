"""笔记 + 链接管理 API"""

import json, os
from fastapi import APIRouter, Depends

from backend.db import get_db

router = APIRouter(tags=["notes"])

LINKS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "custom_links.json")


# ─── 笔记 ───

@router.get("/notes")
def list_notes(db=Depends(get_db)):
    return db.get_all_notes()


@router.post("/notes")
def create_note(body: dict, db=Depends(get_db)):
    nid = db.upsert_note(title=body.get("title", ""), content=body.get("content", ""))
    return {"id": nid}


@router.put("/notes/{note_id}")
def update_note(note_id: int, body: dict, db=Depends(get_db)):
    db.upsert_note(note_id=note_id, title=body.get("title", ""), content=body.get("content", ""))
    return {"ok": True}


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db=Depends(get_db)):
    db.delete_note(note_id)
    return {"ok": True}


# ─── 链接 ───

def _load_links():
    if os.path.exists(LINKS_FILE):
        try:
            with open(LINKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_links(links: list):
    os.makedirs(os.path.dirname(LINKS_FILE), exist_ok=True)
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)


@router.get("/links")
def list_links():
    return _load_links()


@router.post("/links")
def add_link(body: dict):
    links = _load_links()
    links.append({"name": body.get("name", ""), "url": body.get("url", ""), "desc": body.get("desc", "")})
    _save_links(links)
    return {"ok": True}


@router.delete("/links/{idx}")
def delete_link(idx: int):
    links = _load_links()
    if 0 <= idx < len(links):
        links.pop(idx)
        _save_links(links)
    return {"ok": True}


# ─── 报告文件 ───

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


@router.get("/reports")
def list_reports():
    """列出 data 目录下所有 md 报告文件"""
    files = []
    if os.path.exists(DATA_DIR):
        for f in sorted(os.listdir(DATA_DIR), reverse=True):
            if f.endswith('.md'):
                path = os.path.join(DATA_DIR, f)
                stat = os.stat(path)
                files.append({
                    "name": f,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    return files


@router.get("/reports/{filename}")
def get_report(filename: str):
    """读取指定 md 报告文件内容"""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path) or not filename.endswith('.md'):
        return {"error": "文件不存在"}
    with open(path, 'r', encoding='utf-8') as f:
        return {"name": filename, "content": f.read()}
