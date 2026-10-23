"""
可恢复的批处理扫描任务调度器 (ResumableBatchScanner)
特性：
1. 断点续扫：任务状态与已处理结果持久化保存在 SQLite 中，支持中断后无缝恢复
2. 频率控制与限流 (Rate Limiting)：防止对金融数据源发起高频冲击
3. 异常自动重试与降级：支持单标的多轮指数退避重试，失败写入本地日志
4. 进度与质量追踪：实时记录成功、失败、跳过、耗时与错误详情
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import os
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("BatchScanner")


@dataclass
class ScanTaskStatus:
    task_id: str
    scope: str
    strategy_name: str
    total_symbols: int
    processed_count: int
    success_count: int
    failed_count: int
    status: str  # 'PENDING', 'RUNNING', 'PAUSED', 'COMPLETED', 'FAILED', 'CANCELLED'
    last_symbol: str
    created_at: str
    updated_at: str
    error_message: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)


class ResumableBatchScanner:
    """可恢复的后台/前台波段扫描任务管理器"""

    def __init__(
        self,
        db_path: str = "data/stock_analysis.db",
        log_file: str = "data/batch_scan_errors.log",
    ):
        self.db_path = db_path
        self.log_file = log_file
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS batch_scan_tasks (
                    task_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    total_symbols INTEGER NOT NULL,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    last_symbol TEXT,
                    symbols_json TEXT NOT NULL,
                    results_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def create_task(
        self,
        task_id: str,
        scope: str,
        strategy_name: str,
        symbols: List[str],
    ) -> ScanTaskStatus:
        """创建或重置扫描任务"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_obj = ScanTaskStatus(
            task_id=task_id,
            scope=scope,
            strategy_name=strategy_name,
            total_symbols=len(symbols),
            processed_count=0,
            success_count=0,
            failed_count=0,
            status="PENDING",
            last_symbol="",
            created_at=now_str,
            updated_at=now_str,
            results=[],
        )

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO batch_scan_tasks (
                    task_id, scope, strategy_name, total_symbols, processed_count,
                    success_count, failed_count, status, last_symbol, symbols_json,
                    results_json, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, 0, 0, 'PENDING', '', ?, '[]', '', ?, ?)
            """, (task_id, scope, strategy_name, len(symbols), json.dumps(symbols), now_str, now_str))
            conn.commit()

        return status_obj

    def get_task(self, task_id: str) -> Optional[ScanTaskStatus]:
        """获取任务当前状态"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM batch_scan_tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None

            results = []
            if row["results_json"]:
                try:
                    results = json.loads(row["results_json"])
                except Exception:
                    pass

            return ScanTaskStatus(
                task_id=row["task_id"],
                scope=row["scope"],
                strategy_name=row["strategy_name"],
                total_symbols=row["total_symbols"],
                processed_count=row["processed_count"],
                success_count=row["success_count"],
                failed_count=row["failed_count"],
                status=row["status"],
                last_symbol=row["last_symbol"] or "",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                error_message=row["error_message"] or "",
                results=results,
            )

    def run_step(
        self,
        task_id: str,
        process_fn: Callable[[str], Optional[Dict[str, Any]]],
        batch_size: int = 5,
        sleep_interval_sec: float = 0.05,
        max_retries: int = 2,
    ) -> Tuple[ScanTaskStatus, bool]:
        """
        单步增量推进扫描任务
        返回: (status, is_finished)
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM batch_scan_tasks WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"扫描任务不存在: {task_id}")

            symbols = json.loads(row["symbols_json"])
            processed_count = row["processed_count"]
            success_count = row["success_count"]
            failed_count = row["failed_count"]
            results = json.loads(row["results_json"] or "[]")

        if processed_count >= len(symbols):
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._update_task_status(task_id, "COMPLETED", processed_count, success_count, failed_count, results, row["last_symbol"] or "", now_str)
            return self.get_task(task_id), True

        # 取出下一个批次的标的
        batch_symbols = symbols[processed_count : processed_count + batch_size]
        last_sym = row["last_symbol"] or ""

        for sym in batch_symbols:
            retries = 0
            res = None
            err_msg = ""
            while retries <= max_retries:
                try:
                    res = process_fn(sym)
                    break
                except Exception as e:
                    retries += 1
                    err_msg = str(e)
                    time.sleep(0.1 * retries)

            last_sym = sym
            processed_count += 1
            if res is not None:
                success_count += 1
                results.append(res)
            else:
                if err_msg:
                    failed_count += 1
                    self._log_error(task_id, sym, err_msg)

            if sleep_interval_sec > 0:
                time.sleep(sleep_interval_sec)

        is_done = processed_count >= len(symbols)
        new_status = "COMPLETED" if is_done else "RUNNING"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._update_task_status(
            task_id=task_id,
            status=new_status,
            processed_count=processed_count,
            success_count=success_count,
            failed_count=failed_count,
            results=results,
            last_symbol=last_sym,
            updated_at=now_str,
        )

        return self.get_task(task_id), is_done

    def _update_task_status(
        self,
        task_id: str,
        status: str,
        processed_count: int,
        success_count: int,
        failed_count: int,
        results: List[Dict[str, Any]],
        last_symbol: str,
        updated_at: str,
        error_message: str = "",
    ):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE batch_scan_tasks SET
                    status = ?,
                    processed_count = ?,
                    success_count = ?,
                    failed_count = ?,
                    results_json = ?,
                    last_symbol = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE task_id = ?
            """, (
                status,
                processed_count,
                success_count,
                failed_count,
                json.dumps(results, ensure_ascii=False),
                last_symbol,
                error_message,
                updated_at,
                task_id,
            ))
            conn.commit()

    def _log_error(self, task_id: str, symbol: str, error: str):
        log_line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Task: {task_id} | Symbol: {symbol} | Error: {error}\n"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
        except Exception:
            pass
