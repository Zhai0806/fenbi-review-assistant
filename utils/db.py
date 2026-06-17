"""数据库操作封装模块

管理 SQLite 数据库的创建、读写、查询操作。
包含三张核心表：knowledge_points, exam_records, question_analysis。
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Optional


class KnowledgeDB:
    """知识库数据库管理器。

    封装所有 SQLite 操作，提供高层 API 用于：
    - 知识点（knowledge_points）的增删改查
    - 模考记录（exam_records）的管理
    - 单题分析（question_analysis）的存储与查询
    """

    def __init__(self, db_path: str = None):
        """初始化数据库连接。

        Args:
            db_path: 数据库文件路径，默认为 data/knowledge_base.db
        """
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), '..', 'data', 'knowledge_base.db'
            )
        # 确保目录存在
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        """创建所有数据表（如果不存在）。"""
        cursor = self.conn.cursor()

        # 知识点表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                point_name TEXT NOT NULL,
                full_label TEXT UNIQUE NOT NULL,
                total_occurrences INTEGER DEFAULT 0,
                correct_count INTEGER DEFAULT 0,
                total_time_sec REAL DEFAULT 0.0,
                time_squared_sum REAL DEFAULT 0.0,
                error_type_distribution TEXT DEFAULT '{}',
                difficulty_distribution TEXT DEFAULT '{}',
                global_accuracy_sum REAL DEFAULT 0.0,
                global_accuracy_count INTEGER DEFAULT 0,
                last_seen_date TEXT,
                trend_data TEXT DEFAULT '[]',
                question_type TEXT DEFAULT ''
            )
        """)

        # 模考记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_path TEXT NOT NULL UNIQUE,
                exam_name TEXT,
                exam_date TEXT,
                total_questions INTEGER,
                correct_questions INTEGER,
                total_time_sec REAL,
                exam_type TEXT DEFAULT '行测'
            )
        """)

        # 单题分析表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_key TEXT REFERENCES exam_records(report_path),
                question_key TEXT UNIQUE,
                is_correct BOOLEAN,
                time_spent_sec REAL,
                global_correct_ratio REAL,
                error_type TEXT,
                is_guessed_correct BOOLEAN DEFAULT 0,
                is_time_anomaly BOOLEAN DEFAULT 0,
                consecutive_error_group INTEGER,
                user_marked BOOLEAN DEFAULT 0,
                your_answer TEXT,
                correct_answer TEXT,
                difficulty TEXT,
                user_note TEXT DEFAULT '',
                source TEXT DEFAULT ''
            )
        """)

        # 诊断结果临时表（用于确认流程）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_diagnosis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_key TEXT NOT NULL,
                report_path TEXT NOT NULL,
                error_type TEXT,
                confidence REAL,
                explanation TEXT,
                is_confirmed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        self.conn.commit()

        # 兼容已有数据库：添加 source 列（如果不存在）
        try:
            cursor.execute("ALTER TABLE question_analysis ADD COLUMN source TEXT DEFAULT ''")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在

        # 兼容已有数据库：添加 question_type 列
        try:
            cursor.execute("ALTER TABLE knowledge_points ADD COLUMN question_type TEXT DEFAULT ''")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在

        # 兼容已有数据库：添加 exam_type 列
        try:
            cursor.execute("ALTER TABLE exam_records ADD COLUMN exam_type TEXT DEFAULT '行测'")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在

    # ======================== 知识点操作 ========================

    def upsert_knowledge_point(
        self,
        module: str,
        point_name: str,
        is_correct: bool = False,
        time_spent: float = 0.0,
        error_type: str = None,
        difficulty: str = None,
        global_accuracy: float = None,
        exam_date: str = None,
        question_type: str = '',
    ):
        """插入或更新知识点记录。

        每次调用会增加 total_occurrences，并根据参数更新其他字段。
        """
        full_label = f"{module}-{point_name}"
        cursor = self.conn.cursor()

        # 检查是否已存在
        cursor.execute(
            "SELECT * FROM knowledge_points WHERE full_label = ?",
            (full_label,)
        )
        row = cursor.fetchone()

        if row is None:
            # 插入新记录
            error_dist = {}
            if error_type:
                error_dist[error_type] = 1
            diff_dist = {}
            if difficulty:
                diff_dist[difficulty] = 1

            cursor.execute("""
                INSERT INTO knowledge_points
                    (module, point_name, full_label, total_occurrences,
                     correct_count, total_time_sec, time_squared_sum,
                     error_type_distribution, difficulty_distribution,
                     global_accuracy_sum, global_accuracy_count,
                     last_seen_date, trend_data, question_type)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                module, point_name, full_label,
                1 if is_correct else 0,
                time_spent or 0.0,
                (time_spent or 0.0) ** 2,
                json.dumps(error_dist, ensure_ascii=False),
                json.dumps(diff_dist, ensure_ascii=False),
                global_accuracy if global_accuracy is not None else 0.0,
                1 if global_accuracy is not None else 0,
                exam_date or datetime.now().strftime('%Y-%m-%d'),
                json.dumps([1 if is_correct else 0], ensure_ascii=False),
                question_type or '',
            ))
        else:
            # 更新已有记录
            row_dict = dict(row)
            new_total = row_dict['total_occurrences'] + 1
            new_correct = row_dict['correct_count'] + (1 if is_correct else 0)
            new_time = (row_dict['total_time_sec'] or 0.0) + (time_spent or 0.0)
            new_time_sq = (row_dict['time_squared_sum'] or 0.0) + (time_spent or 0.0) ** 2

            # 更新错误类型分布
            error_dist = json.loads(row_dict['error_type_distribution'] or '{}')
            if error_type:
                error_dist[error_type] = error_dist.get(error_type, 0) + 1

            # 更新难度分布
            diff_dist = json.loads(row_dict['difficulty_distribution'] or '{}')
            if difficulty:
                diff_dist[difficulty] = diff_dist.get(difficulty, 0) + 1

            # 更新全站正确率
            new_ga_sum = (row_dict['global_accuracy_sum'] or 0.0)
            new_ga_count = row_dict['global_accuracy_count'] or 0
            if global_accuracy is not None:
                new_ga_sum += global_accuracy
                new_ga_count += 1

            # 更新趋势数据（保留最近10个）
            trend = json.loads(row_dict['trend_data'] or '[]')
            trend.append(1 if is_correct else 0)
            if len(trend) > 10:
                trend = trend[-10:]

            cursor.execute("""
                UPDATE knowledge_points SET
                    total_occurrences = ?, correct_count = ?,
                    total_time_sec = ?, time_squared_sum = ?,
                    error_type_distribution = ?, difficulty_distribution = ?,
                    global_accuracy_sum = ?, global_accuracy_count = ?,
                    last_seen_date = ?, trend_data = ?,
                    question_type = COALESCE(NULLIF(?, ''), question_type)
                WHERE full_label = ?
            """, (
                new_total, new_correct, new_time, new_time_sq,
                json.dumps(error_dist, ensure_ascii=False),
                json.dumps(diff_dist, ensure_ascii=False),
                new_ga_sum, new_ga_count,
                exam_date or datetime.now().strftime('%Y-%m-%d'),
                json.dumps(trend, ensure_ascii=False),
                question_type or '',
                full_label
            ))

        self.conn.commit()

    def get_knowledge_point(self, full_label: str) -> Optional[dict]:
        """根据 full_label 获取知识点详情。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM knowledge_points WHERE full_label = ?",
            (full_label,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_knowledge_points(self) -> list[dict]:
        """获取所有知识点记录。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM knowledge_points ORDER BY module, point_name")
        return [dict(row) for row in cursor.fetchall()]

    def get_modules_summary(self) -> list[dict]:
        """获取各模块汇总统计。

        Returns:
            list[dict]: 每个模块的正确率、平均用时、题数等
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                module,
                question_type,
                SUM(total_occurrences) as total_q,
                SUM(correct_count) as correct_q,
                SUM(total_time_sec) as total_time,
                COUNT(*) as point_count,
                AVG(CASE WHEN global_accuracy_count > 0
                    THEN global_accuracy_sum / global_accuracy_count
                    ELSE NULL END) as avg_global_accuracy
            FROM knowledge_points
            GROUP BY module, question_type
            ORDER BY module, question_type
        """)
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            total = r['total_q'] or 0
            correct = r['correct_q'] or 0
            r['accuracy'] = correct / total if total > 0 else 0.0
            r['avg_time'] = (r['total_time'] or 0.0) / total if total > 0 else 0.0
        return rows

    def get_weak_points(self, limit: int = 10, order_by: str = 'error_count') -> list[dict]:
        """获取薄弱知识点排行。

        Args:
            limit: 返回数量
            order_by: 'error_count' 按错误次数降序，'accuracy' 按正确率升序

        Returns:
            list[dict]: 薄弱知识点列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                full_label, module, question_type, point_name,
                total_occurrences, correct_count,
                (total_occurrences - correct_count) as error_count,
                CAST(correct_count AS REAL) / MAX(total_occurrences, 1) as accuracy,
                total_time_sec,
                error_type_distribution,
                trend_data
            FROM knowledge_points
            WHERE total_occurrences > 0
        """)
        rows = [dict(row) for row in cursor.fetchall()]

        if order_by == 'accuracy':
            rows.sort(key=lambda r: r['accuracy'])
        else:
            rows.sort(key=lambda r: r['error_count'], reverse=True)

        return rows[:limit]

    def get_time_anomaly_points(self, limit: int = 5) -> list[dict]:
        """获取用时异常知识点（按用时偏离度降序）。

        用时偏离度 = (该点平均用时 / 全局平均用时)，值越大越异常。
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                full_label, module, point_name,
                total_occurrences, total_time_sec,
                CASE WHEN total_occurrences > 0
                    THEN total_time_sec / total_occurrences
                    ELSE 0 END as avg_time
            FROM knowledge_points
            WHERE total_occurrences >= 3
        """)
        rows = [dict(row) for row in cursor.fetchall()]

        # 计算全局平均
        all_avg = sum(r['avg_time'] for r in rows) / max(len(rows), 1)
        for r in rows:
            r['deviation_ratio'] = r['avg_time'] / all_avg if all_avg > 0 else 1.0

        rows.sort(key=lambda r: r['deviation_ratio'], reverse=True)
        return rows[:limit]

    def get_global_accuracy_gap(self, limit: int = 10) -> list[dict]:
        """获取全站正确率偏离度分析（你的正确率远低于全站正确率的知识点）。

        Returns:
            list[dict]: 按偏离度降序排列
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                full_label, module, question_type, point_name,
                total_occurrences, correct_count,
                CAST(correct_count AS REAL) / MAX(total_occurrences, 1) as my_accuracy,
                CASE WHEN global_accuracy_count > 0
                    THEN global_accuracy_sum / global_accuracy_count
                    ELSE NULL END as avg_global_accuracy
            FROM knowledge_points
            WHERE total_occurrences >= 2 AND global_accuracy_count > 0
        """)
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            gap = (r['avg_global_accuracy'] or 0) - (r['my_accuracy'] or 0)
            r['gap'] = gap

        rows.sort(key=lambda r: r['gap'], reverse=True)
        return rows[:limit]

    def get_kp_trend(self, full_label: str) -> list:
        """获取指定知识点的趋势数据（最近10次正确率快照）。"""
        kp = self.get_knowledge_point(full_label)
        if kp and kp.get('trend_data'):
            return json.loads(kp['trend_data'])
        return []

    # ======================== 模考记录操作 ========================

    def insert_exam_record(
        self,
        report_path: str,
        exam_name: str = None,
        exam_date: str = None,
        total_questions: int = 0,
        correct_questions: int = 0,
        total_time_sec: float = 0.0,
        exam_type: str = '行测',
    ) -> int:
        """插入一条模考记录，返回记录 ID。"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO exam_records
                (report_path, exam_name, exam_date, total_questions,
                 correct_questions, total_time_sec, exam_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (report_path, exam_name, exam_date, total_questions,
              correct_questions, total_time_sec, exam_type))
        self.conn.commit()
        return cursor.lastrowid

    def update_exam_date(self, report_path: str, new_date: str):
        """更新模考记录的考试日期。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE exam_records SET exam_date = ? WHERE report_path = ?",
            (new_date, report_path)
        )
        self.conn.commit()

    def get_exam_records(self) -> list[dict]:
        """获取所有模考记录，按日期降序。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM exam_records ORDER BY exam_date DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_exam_by_path(self, report_path: str) -> Optional[dict]:
        """根据报告路径查询模考记录。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM exam_records WHERE report_path = ?",
            (report_path,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def exam_exists(self, report_path: str) -> bool:
        """检查某份报告是否已入库。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM exam_records WHERE report_path = ?",
            (report_path,)
        )
        return cursor.fetchone()[0] > 0

    # ======================== 单题分析操作 ========================

    def upsert_question_analysis(self, data: dict):
        """插入或更新单题分析记录。

        Args:
            data: 包含 question_analysis 表各字段的字典。
        """
        cursor = self.conn.cursor()
        qk = data.get('question_key', '')
        cursor.execute(
            "SELECT id FROM question_analysis WHERE question_key = ?",
            (qk,)
        )
        exists = cursor.fetchone()

        if exists:
            # 更新（只更新可变更的字段）
            updatable = ['error_type', 'is_guessed_correct', 'is_time_anomaly',
                         'consecutive_error_group', 'user_marked', 'user_note', 'source',
                         'your_answer', 'correct_answer', 'global_correct_ratio',
                         'time_spent_sec', 'difficulty']
            sets = []
            values = []
            for k in updatable:
                if k in data:
                    sets.append(f"{k} = ?")
                    values.append(data[k])
            if sets:
                values.append(qk)
                cursor.execute(
                    f"UPDATE question_analysis SET {', '.join(sets)} WHERE question_key = ?",
                    values
                )
        else:
            fields = ['report_key', 'question_key', 'is_correct', 'time_spent_sec',
                      'global_correct_ratio', 'error_type', 'is_guessed_correct',
                      'is_time_anomaly', 'consecutive_error_group', 'user_marked',
                      'your_answer', 'correct_answer', 'difficulty', 'user_note', 'source']
            values = [data.get(f) for f in fields]
            placeholders = ', '.join(['?'] * len(fields))
            cursor.execute(
                f"INSERT INTO question_analysis ({', '.join(fields)}) VALUES ({placeholders})",
                values
            )

        self.conn.commit()

    @staticmethod
    def _normalize_paths(path: str) -> list[str]:
        """生成路径的多种形式，用于兼容相对/绝对路径的不一致存储。"""
        candidates = [path]
        try:
            abs_path = os.path.abspath(path)
            if abs_path != path:
                candidates.append(abs_path)
        except Exception:
            pass
        # 去重，保留原始分隔符
        return list(dict.fromkeys(candidates))

    def get_questions_by_report(self, report_path: str) -> list[dict]:
        """获取指定报告的所有题目分析。"""
        cursor = self.conn.cursor()
        for rp in self._normalize_paths(report_path):
            cursor.execute(
                "SELECT * FROM question_analysis WHERE report_key = ? ORDER BY id",
                (rp,)
            )
            rows = cursor.fetchall()
            if rows:
                return [dict(row) for row in rows]
        return []

    def get_question_by_key(self, question_key: str) -> Optional[dict]:
        """获取指定题目的分析记录。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM question_analysis WHERE question_key = ?",
            (question_key,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_question_field(self, question_key: str, field: str, value: Any):
        """更新单题分析的某个字段。"""
        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE question_analysis SET {field} = ? WHERE question_key = ?",
            (value, question_key)
        )
        self.conn.commit()

    # -- 以下是针对知识点的错误类型分布字段的回填操作 --
    def update_kp_error_type_distribution(self, full_label: str, error_type: str):
        """在知识点的 error_type_distribution JSON 中给指定类型 +1。"""
        kp = self.get_knowledge_point(full_label)
        if not kp:
            return
        dist = json.loads(kp.get('error_type_distribution') or '{}')
        dist[error_type] = dist.get(error_type, 0) + 1
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE knowledge_points SET error_type_distribution = ? WHERE full_label = ?",
            (json.dumps(dist, ensure_ascii=False), full_label)
        )
        self.conn.commit()

    def get_error_type_distribution(self) -> dict:
        """获取全局错误类型分布（合并所有知识点）。"""
        points = self.get_all_knowledge_points()
        merged = {}
        for kp in points:
            dist = json.loads(kp.get('error_type_distribution') or '{}')
            for et, count in dist.items():
                merged[et] = merged.get(et, 0) + count
        return merged

    def get_error_type_by_module(self) -> list[dict]:
        """按模块→题型获取错误类型分布。

        Returns:
            list[dict]: [{module, question_type, error_type, count}, ...]
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT module, question_type, error_type_distribution FROM knowledge_points"
        )
        rows = cursor.fetchall()
        result = {}
        for r in rows:
            mod = r[0] or '未知'
            qt = r[1] or mod
            dist = json.loads(r[2] or '{}')
            for et, count in dist.items():
                key = (mod, qt, et)
                result[key] = result.get(key, 0) + count
        return [
            {'module': mod, 'question_type': qt, 'error_type': et, 'count': c}
            for (mod, qt, et), c in sorted(result.items(), key=lambda x: -x[1])
        ]

    # ======================== 诊断确认操作 ========================

    def insert_pending_diagnosis(self, question_key: str, report_path: str,
                                  error_type: str, confidence: float,
                                  explanation: str):
        """插入待确认的诊断结果。"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO pending_diagnosis
                (question_key, report_path, error_type, confidence, explanation)
            VALUES (?, ?, ?, ?, ?)
        """, (question_key, report_path, error_type, confidence, explanation))
        self.conn.commit()

    def get_pending_diagnoses(self, report_path: str = None) -> list[dict]:
        """获取待确认的诊断结果。"""
        cursor = self.conn.cursor()
        if report_path:
            for rp in self._normalize_paths(report_path):
                cursor.execute(
                    "SELECT * FROM pending_diagnosis WHERE is_confirmed = 0 AND report_path = ?",
                    (rp,)
                )
                rows = cursor.fetchall()
                if rows:
                    return [dict(row) for row in rows]
            return []
        else:
            cursor.execute(
                "SELECT * FROM pending_diagnosis WHERE is_confirmed = 0"
            )
            return [dict(row) for row in cursor.fetchall()]

    def confirm_diagnosis(self, diagnosis_id: int, final_error_type: str = None):
        """确认诊断结果并写入 question_analysis 和 knowledge_points。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM pending_diagnosis WHERE id = ?",
            (diagnosis_id,)
        )
        row = cursor.fetchone()
        if not row:
            return

        row_dict = dict(row)
        error_type = final_error_type or row_dict['error_type']

        # 更新 question_analysis
        cursor.execute(
            "UPDATE question_analysis SET error_type = ? WHERE question_key = ?",
            (error_type, row_dict['question_key'])
        )

        # 标记已确认
        cursor.execute(
            "UPDATE pending_diagnosis SET is_confirmed = 1, error_type = ? WHERE id = ?",
            (error_type, diagnosis_id)
        )

        # 同步更新知识点错误类型分布
        qa = self.get_question_by_key(row_dict['question_key'])
        if qa and qa.get('report_key'):
            self._sync_kp_error_type(qa['report_key'], row_dict['question_key'], error_type)

        self.conn.commit()

    def _sync_kp_error_type(self, report_path: str, question_key: str, error_type: str):
        """根据题目 key 找到对应知识点，更新其 error_type_distribution。"""
        import json as _json
        import os as _os
        from .analysis import classify_module, classify_question_type

        # 兼容相对/绝对路径
        file_path = report_path
        if not _os.path.exists(file_path):
            abs_path = _os.path.abspath(report_path)
            if _os.path.exists(abs_path):
                file_path = abs_path
            else:
                return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                questions = _json.load(f)
            if isinstance(questions, dict):
                questions = questions.get('questions', questions.get('data', []))
            if not isinstance(questions, list):
                return
        except (_json.JSONDecodeError, IOError):
            return

        # 找到对应题目
        target_q = None
        for q in questions:
            if not isinstance(q, dict):
                continue
            if q.get('key', '') == question_key:
                target_q = q
                break
        if not target_q:
            return

        kps = target_q.get('keypoints', [])
        if not kps:
            return

        # 归类并更新每个知识点
        all_names = [kp.get('name', '') for kp in kps]
        mod_map = classify_module(list(set(all_names)))
        name_to_mod = {}
        for mod, names in mod_map.items():
            for n in names:
                name_to_mod[n] = mod

        cursor = self.conn.cursor()
        for kp in kps:
            kp_name = kp.get('name', '')
            if not kp_name:
                continue
            mod = name_to_mod.get(kp_name, '其他')
            full_label = f"{mod}-{kp_name}"

            cursor.execute(
                "SELECT error_type_distribution FROM knowledge_points WHERE full_label = ?",
                (full_label,)
            )
            row = cursor.fetchone()
            if row:
                dist = _json.loads(row[0] or '{}')
                dist[error_type] = dist.get(error_type, 0) + 1
                cursor.execute(
                    "UPDATE knowledge_points SET error_type_distribution = ? WHERE full_label = ?",
                    (_json.dumps(dist, ensure_ascii=False), full_label)
                )

    # ======================== 统计查询 ========================

    def get_guessed_correct_count(self) -> int:
        """获取蒙对题总数。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM question_analysis WHERE is_guessed_correct = 1"
        )
        return cursor.fetchone()[0]

    def get_guessed_correct_distribution(self) -> list[dict]:
        """蒙对题按模块分布。"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT kp.module, COUNT(*) as cnt
            FROM question_analysis qa
            JOIN knowledge_points kp ON qa.question_key LIKE '%'
            WHERE qa.is_guessed_correct = 1
            GROUP BY kp.module
        """)
        # 由于 question_key 与 full_label 没有直接外键关联，改用子查询方式
        # 这里返回简单的计数
        return [dict(row) for row in cursor.fetchall()]

    def get_consecutive_error_groups(self, report_path: str = None) -> list[dict]:
        """获取连续错题组。"""
        cursor = self.conn.cursor()
        query = """
            SELECT consecutive_error_group, COUNT(*) as error_count,
                   MIN(id) as start_id, MAX(id) as end_id
            FROM question_analysis
            WHERE consecutive_error_group IS NOT NULL AND consecutive_error_group > 0
        """
        params = []
        if report_path:
            query += " AND report_key = ?"
            params.append(report_path)
        query += " GROUP BY consecutive_error_group HAVING error_count >= 3"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_db_context_for_chat(self) -> str:
        """生成供 AI 对话使用的知识库统计摘要。

        Returns:
            str: 格式化的统计信息文本
        """
        modules = self.get_modules_summary()
        weak = self.get_weak_points(limit=10)
        error_dist = self.get_error_type_distribution()
        guessed = self.get_guessed_correct_count()
        exams = self.get_exam_records()

        lines = [f"## 知识库统计摘要（共 {len(exams)} 次模考记录）\n"]

        # 各模块概况
        lines.append("### 各模块正确率")
        for m in modules:
            lines.append(
                f"- {m['module']}：{m['total_q']}题，"
                f"正确率 {m['accuracy']:.1%}，"
                f"平均用时 {m['avg_time']:.1f}秒"
            )

        # 薄弱知识点
        lines.append("\n### 薄弱知识点 Top 10")
        for i, w in enumerate(weak, 1):
            lines.append(
                f"{i}. {w['full_label']}：{w['error_count']}/{w['total_occurrences']}错，"
                f"正确率 {w['accuracy']:.1%}"
            )

        # 错误类型分布
        if error_dist:
            lines.append("\n### 错误类型分布")
            total_errors = sum(error_dist.values())
            for et, cnt in sorted(error_dist.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"- {et}：{cnt}次（{cnt/total_errors:.1%}）")

        lines.append(f"\n### 蒙对题总数：{guessed}")

        return '\n'.join(lines)

    def close(self):
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
