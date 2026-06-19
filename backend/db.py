"""数据库连接管理 —— 封装现有 KnowledgeDB，提供依赖注入"""

import os
from utils.db import KnowledgeDB

_db_instance: KnowledgeDB | None = None


def init_db():
    global _db_instance
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "knowledge_base.db")
    _db_instance = KnowledgeDB(db_path)


def get_db() -> KnowledgeDB:
    assert _db_instance is not None, "DB 未初始化"
    return _db_instance
