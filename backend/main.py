"""粉笔模考复盘助手 - FastAPI 后端入口"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 项目根目录加入路径，复用现有 utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api import exams, questions, diagnose, insights, chat, shenlun, notes
from backend.db import get_db, init_db

app = FastAPI(title="粉笔模考复盘助手 API", version="2.0.0")

# CORS（开发时允许前端 5173 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


app.include_router(exams.router, prefix="/api")
app.include_router(questions.router, prefix="/api")
app.include_router(diagnose.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(shenlun.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
