#!/usr/bin/env python3
"""
WQB 精准突破因子回测与提交脚本
=================================

策略：用更快的衰减(d5/d3)降低自相关性，同时用少量短周期波动率权重补充Fitness，
      精准卡在 SELF_CORRELATION≤0.7 且 Fitness≥1.0 的交集区域。

功能：
  1. 提交12个精准设计的因子到 WQB 平台回测
  2. 自动去重（基于表达式+设置哈希）
  3. 等待回测结果，支持断点续跑
  4. 筛选 Sharpe≥1.25 且 Fitness≥1.0 的因子
  5. 对达标因子执行8项提交检查
  6. 通过全部检查的因子自动正式提交
  7. 生成详细分析报告

因子分组（12个）：
  组1：短衰减纯alpha_021（基线） - 3个
  组2：d5基础 + 少量vol20（精准卡阈值区） - 4个
  组3：d3基础 + 少量vol20（自相关更低） - 3个
  组4：变化率+条件过滤（提升Fitness） - 2个

状态库：wqb_state.db
  - alphas表：按表达式+完整设置哈希去重，存储回测结果
  - submit_checks表：存储提交检查结果
"""

import asyncio
import json
import os
import sys
import time
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager

import requests

# ============================================================
# 路径配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================
# 工具 Schema 版本常量
# ============================================================

TOOL_SCHEMA_VERSIONS = {
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "file_to_url": "v1_fe3416acf3d7b53b",
}

# ============================================================
# 常量配置
# ============================================================

BASE_URL = "https://api.worldquantbrain.com"

# 基准提交设置
DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "maxTrade": "ON",
    "pasteurization": "ON",
    "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}

# 8项提交检查阈值
SUBMISSION_CHECKS = {
    "LOW_SHARPE": 1.25,
    "LOW_FITNESS": 1.0,
    "LOW_TURNOVER": 0.01,
    "HIGH_TURNOVER": 0.7,
    "CONCENTRATED_WEIGHT": None,
    "LOW_SUB_UNIVERSE_SHARPE": None,
    "SELF_CORRELATION": 0.7,
    "MATCHES_COMPETITION": None,
}

# ============================================================
# 因子定义（12个，分4组）
# ============================================================

# alpha_021 基础表达式: open/ts_delay(close,1) - close/open
# 注意: WQB FASTEXPR 使用 ts_delay 而非 shift
ALPHA_021_BASE = "subtract(divide(open, ts_delay(close, 1)), divide(close, open))"

# volatility_20: ts_std_dev(log(close/ts_delay(close,1)), 20) * sqrt(252)
VOL_20 = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"

# returns (简单收益率): close/ts_delay(close,1) - 1
RETURNS = "subtract(divide(close, ts_delay(close, 1)), 1)"

FACTOR_LIST = [
    # ===== 组1：短衰减纯alpha_021（基线） =====
    (
        "alpha_021_d5",
        "baseline_d5",
        # ts_decay_linear(open/shift(close,1) - close/open, 5)
        f"ts_decay_linear({ALPHA_021_BASE}, 5)"
    ),
    (
        "alpha_021_d3",
        "baseline_d3",
        # ts_decay_linear(open/shift(close,1) - close/open, 3)
        f"ts_decay_linear({ALPHA_021_BASE}, 3)"
    ),
    (
        "alpha_021_d1_raw",
        "baseline_raw",
        # 无衰减原始信号: open/shift(close,1) - close/open
        ALPHA_021_BASE
    ),

    # ===== 组2：d5基础 + 少量vol20（精准卡阈值区） =====
    (
        "combo_d5_vol20_w9505",
        "combo_d5_vol",
        # 0.95*alpha_021_d5 + 0.05*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.95, ts_decay_linear({ALPHA_021_BASE}, 5)), "
        f"multiply(0.05, -ts_rank({VOL_20}, 20)))"
    ),
    (
        "combo_d5_vol20_w9010",
        "combo_d5_vol",
        # 0.9*alpha_021_d5 + 0.1*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.9, ts_decay_linear({ALPHA_021_BASE}, 5)), "
        f"multiply(0.1, -ts_rank({VOL_20}, 20)))"
    ),
    (
        "combo_d5_vol20_w8515",
        "combo_d5_vol",
        # 0.85*alpha_021_d5 + 0.15*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.85, ts_decay_linear({ALPHA_021_BASE}, 5)), "
        f"multiply(0.15, -ts_rank({VOL_20}, 20)))"
    ),
    (
        "combo_d5_vol20_w8020",
        "combo_d5_vol",
        # 0.8*alpha_021_d5 + 0.2*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.8, ts_decay_linear({ALPHA_021_BASE}, 5)), "
        f"multiply(0.2, -ts_rank({VOL_20}, 20)))"
    ),

    # ===== 组3：d3基础 + 少量vol20（自相关更低，需要更多vol补Fitness） =====
    (
        "combo_d3_vol20_w9010",
        "combo_d3_vol",
        # 0.9*alpha_021_d3 + 0.1*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.9, ts_decay_linear({ALPHA_021_BASE}, 3)), "
        f"multiply(0.1, -ts_rank({VOL_20}, 20)))"
    ),
    (
        "combo_d3_vol20_w8020",
        "combo_d3_vol",
        # 0.8*alpha_021_d3 + 0.2*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.8, ts_decay_linear({ALPHA_021_BASE}, 3)), "
        f"multiply(0.2, -ts_rank({VOL_20}, 20)))"
    ),
    (
        "combo_d3_vol20_w7030",
        "combo_d3_vol",
        # 0.7*alpha_021_d3 + 0.3*(-ts_rank(volatility_20, 20))
        f"add(multiply(0.7, ts_decay_linear({ALPHA_021_BASE}, 3)), "
        f"multiply(0.3, -ts_rank({VOL_20}, 20)))"
    ),

    # ===== 组4：变化率+条件过滤（提升Fitness） =====
    (
        "extreme_day_reversal_filtered",
        "conditional_filter",
        # trade_when(abs(returns) > ts_mean(abs(returns), 20)*1.5, -1*returns, 0)
        f"trade_when(multiply(-1, {RETURNS}), "
        f"greater(abs({RETURNS}), multiply(ts_mean(abs({RETURNS}), 20), 1.5)), "
        f"0)"
    ),
    (
        "high_vol_reversal_v2",
        "conditional_filter",
        # trade_when(volume > ts_mean(volume, 20)*1.5, -1*(close-open)/close, 0)
        f"trade_when(multiply(-1, divide(subtract(close, open), close)), "
        f"greater(volume, multiply(ts_mean(volume, 20), 1.5)), "
        f"0)"
    ),
]

# 因子分组元数据
FACTOR_GROUPS = {
    "组1：短衰减纯alpha_021（基线）": [
        "alpha_021_d5", "alpha_021_d3", "alpha_021_d1_raw"
    ],
    "组2：d5基础 + vol20（精准卡阈值区）": [
        "combo_d5_vol20_w9505", "combo_d5_vol20_w9010",
        "combo_d5_vol20_w8515", "combo_d5_vol20_w8020"
    ],
    "组3：d3基础 + vol20（自相关更低）": [
        "combo_d3_vol20_w9010", "combo_d3_vol20_w8020", "combo_d3_vol20_w7030"
    ],
    "组4：条件过滤型（提升Fitness）": [
        "extreme_day_reversal_filtered", "high_vol_reversal_v2"
    ],
}


# ============================================================
# 指数退避重试
# ============================================================

def retry_with_backoff(func, *args, max_retries: int = 5,
                       base_delay: float = 3.0, backoff_factor: float = 2.0,
                       status_codes: tuple = (429, 500, 502, 503, 504),
                       **kwargs):
    """指数退避重试包装器"""
    delay = base_delay
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response.status_code in status_codes:
                last_exception = e
                retry_after = e.response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay * (backoff_factor ** attempt)
                print(f"  [重试 {attempt+1}/{max_retries}] 状态码 {e.response.status_code}, "
                      f"等待 {wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                raise
    raise last_exception


# ============================================================
# WQB API 客户端
# ============================================================

class WQBPrecisionClient:
    """精准突破因子专用 WQB 客户端"""

    def __init__(self, email: str, password: str, db_path: str):
        # 清除代理环境变量
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                    "ALL_PROXY", "all_proxy"]:
            if var in os.environ:
                del os.environ[var]

        self.email = email
        self._session = requests.Session()
        self._session.auth = (email, password)
        self._session.trust_env = False
        self._authenticated = False
        self.db_path = db_path

    def authenticate(self) -> dict:
        """登录认证"""
        def _do():
            response = self._session.post(f"{BASE_URL}/authentication")
            response.raise_for_status()
            return response.json()

        user_info = retry_with_backoff(_do, max_retries=3)
        self._authenticated = True
        print(f"[WQB] 登录成功: {user_info.get('user', {}).get('id', 'unknown')}")
        return user_info

    # ---- 模拟提交 ----

    def submit_simulation(self, expression: str, settings: dict = None) -> str:
        """提交模拟，返回 progress URL"""
        sim_settings = dict(DEFAULT_SETTINGS)
        if settings:
            sim_settings.update(settings)

        payload = {
            "type": "REGULAR",
            "settings": sim_settings,
            "regular": expression,
        }

        def _do():
            response = self._session.post(f"{BASE_URL}/simulations", json=payload)
            response.raise_for_status()
            return response.headers.get("Location")

        return retry_with_backoff(_do, max_retries=3, base_delay=5.0)

    def poll_simulation(self, progress_url: str) -> Tuple[str, Optional[str]]:
        """
        轮询模拟进度
        Returns: (status, alpha_id)
          status: "PENDING" | "COMPLETED" | "FAILED"
        """
        try:
            def _do():
                return self._session.get(progress_url)

            response = retry_with_backoff(_do, max_retries=3, base_delay=2.0)
            retry_after = float(response.headers.get("Retry-After", 0))

            if retry_after == 0:
                response.raise_for_status()
                result = response.json()
                alpha_id = result.get("alpha")
                return "COMPLETED", alpha_id
            else:
                return "PENDING", None
        except Exception as e:
            print(f"  [轮询错误] {e}")
            return "FAILED", None

    def get_alpha(self, alpha_id: str) -> dict:
        """获取 Alpha 详情"""
        def _do():
            response = self._session.get(f"{BASE_URL}/alphas/{alpha_id}")
            response.raise_for_status()
            return response.json()

        return retry_with_backoff(_do, max_retries=3)

    # ---- 提交检查 ----

    def run_submit_check(self, alpha_id: str) -> dict:
        """
        运行提交检查（POST /alphas/{id}/submit）
        
        注意：403是正常的（检查未通过），响应体中包含检查结果。
        检查结果在 is.checks 数组中。
        
        Returns:
            dict with:
              - status: "PASS" | "FAIL" | "PENDING"
              - checks: {check_name: {status, value, limit}}
              - self_correlation: float or None
              - sharpe: float or None
              - fitness: float or None
              - turnover: float or None
              - raw: 原始响应数据
        """
        def _do_post():
            return self._session.post(f"{BASE_URL}/alphas/{alpha_id}/submit")

        try:
            response = retry_with_backoff(
                _do_post, max_retries=3, base_delay=5.0,
                status_codes=(429, 500, 502, 503, 504)
            )
            if response.status_code in (403, 200, 201, 202):
                try:
                    data = response.json()
                except Exception:
                    data = {}
            else:
                response.raise_for_status()
                data = response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                try:
                    data = e.response.json()
                except Exception:
                    data = {}
            else:
                raise

        # 解析 IS 指标
        is_data = data.get("is", {})

        # 解析检查结果
        checks_list = is_data.get("checks", [])
        checks_dict = {}
        all_pass = True
        has_pending = False
        self_corr_value = None
        sharpe = None
        fitness = None
        turnover = None

        for check in checks_list:
            name = check.get("name", "UNKNOWN")
            result = check.get("result", "UNKNOWN")
            value = check.get("value")
            limit = check.get("limit")
            checks_dict[name] = {
                "status": result,
                "value": value,
                "limit": limit,
            }
            # 从检查项中提取关键指标
            if name == "SELF_CORRELATION" and value is not None:
                try:
                    self_corr_value = float(value)
                except (ValueError, TypeError):
                    pass
            elif name == "LOW_SHARPE" and value is not None:
                try:
                    sharpe = float(value)
                except (ValueError, TypeError):
                    pass
            elif name == "LOW_FITNESS" and value is not None:
                try:
                    fitness = float(value)
                except (ValueError, TypeError):
                    pass
            elif name == "LOW_TURNOVER" and value is not None:
                try:
                    turnover = float(value)
                except (ValueError, TypeError):
                    pass

            if result == "FAIL":
                all_pass = False
            elif result == "PENDING":
                has_pending = True

        if has_pending:
            overall_status = "PENDING"
        elif all_pass and checks_dict:
            overall_status = "PASS"
        else:
            overall_status = "FAIL"

        return {
            "status": overall_status,
            "checks": checks_dict,
            "self_correlation": self_corr_value,
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": turnover,
            "raw": data,
        }

    def confirm_submit(self, alpha_id: str) -> dict:
        """
        正式提交 Alpha（通过所有检查后再次调用 submit 接口）
        PUT /alphas/{id}/submit
        """
        def _do_put():
            return self._session.put(f"{BASE_URL}/alphas/{alpha_id}/submit")

        response = retry_with_backoff(
            _do_put, max_retries=3, base_delay=5.0,
            status_codes=(429, 500, 502, 503, 504)
        )
        response.raise_for_status()
        return response.json()

    # ---- 数据库操作 ----

    @contextmanager
    def _db_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _expr_hash(expression: str, settings: dict) -> str:
        """计算表达式+设置的哈希值（去重键）"""
        # 规范化：确保settings排序一致
        normalized_settings = json.dumps(settings, sort_keys=True)
        key = json.dumps({"expr": expression, "settings": normalized_settings}, sort_keys=True)
        return hashlib.md5(key.encode()).hexdigest()

    def _ensure_tables(self):
        """确保数据库表存在"""
        with self._db_conn() as conn:
            # alphas 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alphas (
                    expr_hash TEXT PRIMARY KEY,
                    expression TEXT NOT NULL,
                    factor_name TEXT,
                    category TEXT,
                    settings_json TEXT NOT NULL,
                    alpha_id TEXT,
                    status TEXT DEFAULT 'PENDING',
                    sharpe REAL,
                    fitness REAL,
                    ic REAL,
                    rank_ic REAL,
                    turnover REAL,
                    annual_return REAL,
                    max_drawdown REAL,
                    is_summary TEXT,
                    yearly_json TEXT,
                    submitted_at TEXT,
                    completed_at TEXT,
                    progress_url TEXT,
                    error TEXT,
                    submit_checks TEXT,
                    submit_status TEXT,
                    submitted_to_live TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alphas_status ON alphas(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alphas_factor ON alphas(factor_name)")

            # submit_checks 表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS submit_checks (
                    alpha_id TEXT NOT NULL,
                    factor_name TEXT,
                    checked_at TEXT NOT NULL,
                    status TEXT,
                    self_correlation REAL,
                    sharpe REAL,
                    fitness REAL,
                    turnover REAL,
                    checks_json TEXT,
                    passed INTEGER,
                    submitted INTEGER DEFAULT 0,
                    submit_result TEXT,
                    error TEXT,
                    PRIMARY KEY (alpha_id, checked_at)
                )
            """)

    def get_factor_status(self, expression: str, settings: dict) -> Optional[dict]:
        """获取因子状态"""
        expr_hash = self._expr_hash(expression, settings)
        with self._db_conn() as conn:
            row = conn.execute(
                "SELECT * FROM alphas WHERE expr_hash = ?", (expr_hash,)
            ).fetchone()
            return dict(row) if row else None

    def save_factor_submitted(self, expression: str, settings: dict,
                              factor_name: str, category: str,
                              progress_url: str):
        """保存已提交的因子（PENDING 状态）"""
        expr_hash = self._expr_hash(expression, settings)
        now = datetime.now().isoformat(timespec="seconds")
        with self._db_conn() as conn:
            existing = conn.execute(
                "SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE alphas SET
                        progress_url = ?, status = 'PENDING',
                        factor_name = ?, category = ?, submitted_at = ?,
                        error = NULL
                    WHERE expr_hash = ?
                """, (progress_url, factor_name, category, now, expr_hash))
            else:
                conn.execute("""
                    INSERT INTO alphas (
                        expr_hash, expression, factor_name, category, settings_json,
                        progress_url, status, submitted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
                """, (
                    expr_hash, expression, factor_name, category,
                    json.dumps(settings, sort_keys=True), progress_url, now
                ))

    def save_factor_completed(self, expression: str, settings: dict,
                              alpha_id: str, metrics: dict):
        """保存因子完成状态和指标"""
        expr_hash = self._expr_hash(expression, settings)
        now = datetime.now().isoformat(timespec="seconds")
        with self._db_conn() as conn:
            conn.execute("""
                UPDATE alphas SET
                    alpha_id = ?, status = 'COMPLETED',
                    sharpe = ?, fitness = ?, turnover = ?,
                    annual_return = ?, max_drawdown = ?,
                    is_summary = ?, completed_at = ?
                WHERE expr_hash = ?
            """, (
                alpha_id,
                metrics.get("sharpe"), metrics.get("fitness"),
                metrics.get("turnover"), metrics.get("annual_return"),
                metrics.get("max_drawdown"),
                json.dumps(metrics.get("is_summary", {}), ensure_ascii=False),
                now, expr_hash
            ))

    def save_factor_failed(self, expression: str, settings: dict, error: str):
        """保存因子失败状态"""
        expr_hash = self._expr_hash(expression, settings)
        now = datetime.now().isoformat(timespec="seconds")
        with self._db_conn() as conn:
            conn.execute("""
                UPDATE alphas SET status = 'FAILED', error = ?, completed_at = ?
                WHERE expr_hash = ?
            """, (error, now, expr_hash))

    def get_pending_factors(self) -> List[dict]:
        """获取所有 PENDING 状态的因子"""
        with self._db_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM alphas WHERE status = 'PENDING' ORDER BY submitted_at"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_target_factors(self, factor_names: List[str]) -> List[dict]:
        """获取指定名称的因子（去重：每个名称取最新完成的）"""
        with self._db_conn() as conn:
            results = []
            seen_names = set()
            # 按 completed_at 倒序，确保每个因子名只保留最新的一条
            rows = conn.execute("""
                SELECT * FROM alphas
                WHERE factor_name IS NOT NULL
                ORDER BY 
                    CASE status WHEN 'COMPLETED' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END,
                    completed_at DESC, submitted_at DESC
            """).fetchall()
            for row in rows:
                d = dict(row)
                name = d.get("factor_name")
                if name in factor_names and name not in seen_names:
                    results.append(d)
                    seen_names.add(name)
            return results

    def save_submit_check(self, alpha_id: str, factor_name: str,
                          status: str, checks: dict,
                          self_correlation: float = None,
                          sharpe: float = None, fitness: float = None,
                          turnover: float = None,
                          error: str = None) -> str:
        """保存提交检查结果到 submit_checks 表"""
        now = datetime.now().isoformat(timespec="seconds")
        passed = 1 if status == "PASS" else 0
        with self._db_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO submit_checks (
                    alpha_id, factor_name, checked_at, status,
                    self_correlation, sharpe, fitness, turnover,
                    checks_json, passed, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alpha_id, factor_name, now, status,
                self_correlation, sharpe, fitness, turnover,
                json.dumps(checks, ensure_ascii=False),
                passed, error
            ))
        return now

    def mark_submitted(self, alpha_id: str, checked_at: str, submit_result: str):
        """标记为已正式提交"""
        with self._db_conn() as conn:
            conn.execute("""
                UPDATE submit_checks SET submitted = 1, submit_result = ?
                WHERE alpha_id = ? AND checked_at = ?
            """, (submit_result, alpha_id, checked_at))

    def update_alpha_submit_status(self, expression: str, settings: dict,
                                   submit_status: str, checks: dict,
                                   submitted_to_live: bool = False):
        """更新 alphas 表的提交状态"""
        expr_hash = self._expr_hash(expression, settings)
        with self._db_conn() as conn:
            conn.execute("""
                UPDATE alphas SET submit_status = ?, submit_checks = ?,
                    submitted_to_live = ?
                WHERE expr_hash = ?
            """, (
                submit_status,
                json.dumps(checks, ensure_ascii=False),
                "YES" if submitted_to_live else None,
                expr_hash
            ))


# ============================================================
# 核心业务流程
# ============================================================

def submit_new_factors(client: WQBPrecisionClient,
                       factors: List[tuple],
                       submit_interval: int = 50) -> int:
    """
    提交新因子到 WQB 平台
    返回新提交的数量
    """
    submitted = 0
    settings = DEFAULT_SETTINGS
    total = len(factors)

    print(f"\n=== 提交新因子（共 {total} 个，间隔 {submit_interval}s）===")

    for i, (name, category, expression) in enumerate(factors):
        # 检查是否已存在
        existing = client.get_factor_status(expression, settings)
        if existing:
            status = existing.get("status", "UNKNOWN")
            if status == "COMPLETED":
                print(f"  [跳过-已完成] {name}: Sharpe={existing.get('sharpe', 'N/A')}, "
                      f"Fitness={existing.get('fitness', 'N/A')}")
                # 更新名字和分类（如果之前没有）
                if not existing.get("factor_name"):
                    with client._db_conn() as conn:
                        expr_hash = client._expr_hash(expression, settings)
                        conn.execute("""
                            UPDATE alphas SET factor_name = ?, category = ?
                            WHERE expr_hash = ?
                        """, (name, category, expr_hash))
                continue
            elif status == "PENDING":
                print(f"  [跳过-进行中] {name}: 已在排队中")
                continue
            elif status == "FAILED":
                print(f"  [重试] {name}: 之前失败，重新提交")
            else:
                print(f"  [跳过] {name}: 状态={status}")
                continue

        print(f"  [{i+1}/{total}] 提交 {name} ({category})")
        try:
            progress_url = client.submit_simulation(expression, settings)
            client.save_factor_submitted(expression, settings, name, category, progress_url)
            submitted += 1
            print(f"    ✓ 提交成功: {progress_url}")
        except Exception as e:
            print(f"    ✗ 提交失败: {e}")
            client.save_factor_failed(expression, settings, f"submit failed: {e}")

        # 提交间隔（最后一个不需要等）
        if i < total - 1:
            print(f"    ⏳ 等待 {submit_interval}s ...")
            time.sleep(submit_interval)

    print(f"\n[完成] 本次新提交 {submitted} 个因子")
    return submitted


def wait_for_results(client: WQBPrecisionClient,
                     poll_interval: int = 15,
                     max_polls: int = 30) -> int:
    """
    等待所有 PENDING 因子完成回测
    返回完成的数量
    """
    pending = client.get_pending_factors()
    if not pending:
        print("[状态] 无待处理的 PENDING 因子")
        return 0

    print(f"\n=== 等待回测结果（{len(pending)} 个因子，最长约{poll_interval*max_polls/60:.0f}分钟）===")

    completed_count = 0
    failed_count = 0

    for poll_round in range(max_polls):
        all_done = True

        for factor in pending:
            if factor["status"] != "PENDING":
                continue
            if not factor.get("progress_url"):
                factor["status"] = "FAILED"
                failed_count += 1
                continue

            try:
                status, alpha_id = client.poll_simulation(factor["progress_url"])

                if status == "COMPLETED" and alpha_id:
                    factor_name = factor.get("factor_name", factor["expr_hash"][:8])
                    print(f"  ✓ {factor_name}: 完成, Alpha ID={alpha_id}")

                    # 获取详细指标
                    try:
                        alpha_data = client.get_alpha(alpha_id)
                        is_data = alpha_data.get("is", {})
                        metrics = {
                            "sharpe": is_data.get("sharpe"),
                            "fitness": is_data.get("fitness"),
                            "turnover": is_data.get("turnover"),
                            "annual_return": is_data.get("returns"),
                            "max_drawdown": is_data.get("drawdown"),
                            "is_summary": is_data,
                        }
                        settings = json.loads(factor["settings_json"])
                        client.save_factor_completed(
                            factor["expression"], settings, alpha_id, metrics
                        )
                        print(f"    Sharpe={metrics['sharpe']}, "
                              f"Fitness={metrics['fitness']}, "
                              f"Turnover={metrics['turnover']}")
                    except Exception as e:
                        print(f"    ⚠️ 获取详情失败: {e}")
                        # 即使获取详情失败，也标记为完成（有alpha_id）
                        settings = json.loads(factor["settings_json"])
                        client.save_factor_completed(
                            factor["expression"], settings, alpha_id, {}
                        )

                    factor["status"] = "COMPLETED"
                    completed_count += 1

                elif status == "FAILED":
                    factor_name = factor.get("factor_name", factor["expr_hash"][:8])
                    print(f"  ✗ {factor_name}: 回测失败")
                    settings = json.loads(factor["settings_json"])
                    client.save_factor_failed(
                        factor["expression"], settings, "simulation failed"
                    )
                    factor["status"] = "FAILED"
                    failed_count += 1
                else:
                    all_done = False
            except Exception as e:
                print(f"  [错误] {factor.get('factor_name', 'unknown')}: {e}")
                all_done = False

        if all_done:
            break

        pending_count = sum(1 for f in pending if f["status"] == "PENDING")
        if poll_round < max_polls - 1 and pending_count > 0:
            print(f"  [第 {poll_round+1}/{max_polls} 轮] 还有 {pending_count} 个因子等待中...")
            time.sleep(poll_interval)

    print(f"\n[完成] 回测完成: 成功 {completed_count} 个, 失败 {failed_count} 个")
    return completed_count


def run_submit_checks(client: WQBPrecisionClient,
                      factor_names: List[str],
                      min_sharpe: float = 1.25,
                      min_fitness: float = 1.0,
                      check_interval: int = 50) -> Tuple[List[dict], List[dict]]:
    """
    对达标因子运行提交检查
    
    Returns: (passed_factors, all_checked_factors)
    """
    print(f"\n=== 提交检查（Sharpe≥{min_sharpe} & Fitness≥{min_fitness}）===")

    # 获取目标因子
    target_factors = client.get_target_factors(factor_names)
    print(f"找到 {len(target_factors)} 个目标因子")

    # 筛选达标因子
    qualified = []
    for f in target_factors:
        sharpe = f.get("sharpe")
        fitness = f.get("fitness")
        if (sharpe is not None and sharpe >= min_sharpe
                and fitness is not None and fitness >= min_fitness):
            qualified.append(f)

    print(f"达标因子: {len(qualified)} 个")
    for f in qualified:
        print(f"  - {f['factor_name']}: Sharpe={f['sharpe']:.2f}, Fitness={f['fitness']:.2f}")

    if not qualified:
        print("  没有达标因子，跳过提交检查")
        return [], []

    # 对每个达标因子做提交检查
    passed = []
    checked = []

    for i, f in enumerate(qualified):
        alpha_id = f.get("alpha_id")
        if not alpha_id:
            print(f"  [跳过] {f['factor_name']}: 无 alpha_id")
            continue

        name = f["factor_name"]
        print(f"\n  [{i+1}/{len(qualified)}] 检查 {name} (alpha={alpha_id})")

        try:
            # 运行提交检查
            check_result = client.run_submit_check(alpha_id)

            # 如果有PENDING的检查项，等待后重试
            if check_result["status"] == "PENDING":
                print(f"    部分检查进行中，等待后重试...")
                for wait_round in range(6):
                    time.sleep(10)
                    check_result = client.run_submit_check(alpha_id)
                    if check_result["status"] != "PENDING":
                        break
                    print(f"    仍在进行中... ({wait_round+1}/6)")

            checks = check_result["checks"]
            all_pass = check_result["status"] == "PASS"
            self_corr = check_result["self_correlation"]
            sharpe_val = check_result["sharpe"]
            fitness_val = check_result["fitness"]
            turnover_val = check_result["turnover"]

            # 输出检查详情
            for check_name, check_info in checks.items():
                check_status = check_info.get("status", "UNKNOWN")
                check_value = check_info.get("value")
                check_limit = check_info.get("limit")
                status_icon = "✓" if check_status == "PASS" else (
                    "✗" if check_status == "FAIL" else "⏳"
                )
                try:
                    val_str = f"={float(check_value):.4f}" if check_value else ""
                except (ValueError, TypeError):
                    val_str = f"={check_value}" if check_value else ""
                lim_str = f" (limit={check_limit})" if check_limit else ""
                print(f"    {status_icon} {check_name}: {check_status}{val_str}{lim_str}")

            print(f"    综合结果: {check_result['status']}")
            if self_corr is not None:
                print(f"    Self-Correlation: {self_corr:.4f}")

            # 保存到 submit_checks 表
            checked_at = client.save_submit_check(
                alpha_id=alpha_id,
                factor_name=name,
                status=check_result["status"],
                checks=checks,
                self_correlation=self_corr,
                sharpe=sharpe_val,
                fitness=fitness_val,
                turnover=turnover_val,
            )

            # 更新 alphas 表
            expr_settings = json.loads(f["settings_json"]) if f.get("settings_json") else DEFAULT_SETTINGS
            client.update_alpha_submit_status(
                f["expression"], expr_settings,
                check_result["status"], checks
            )

            result = {
                "factor": f,
                "alpha_id": alpha_id,
                "factor_name": name,
                "checks": checks,
                "all_pass": all_pass,
                "overall_status": check_result["status"],
                "self_correlation": self_corr,
                "sharpe": sharpe_val,
                "fitness": fitness_val,
                "turnover": turnover_val,
                "checked_at": checked_at,
                "submitted": False,
            }
            checked.append(result)

            if all_pass:
                passed.append(result)
                print(f"    ★ 全部通过！可以正式提交")

        except Exception as e:
            print(f"    ✗ 检查失败: {e}")
            import traceback
            traceback.print_exc()

            checked.append({
                "factor": f,
                "alpha_id": alpha_id,
                "factor_name": name,
                "checks": {},
                "all_pass": False,
                "overall_status": "ERROR",
                "error": str(e),
                "submitted": False,
            })

        # 检查间隔（最后一个不需要等）
        if i < len(qualified) - 1:
            print(f"    ⏳ 等待 {check_interval}s ...")
            time.sleep(check_interval)

    return passed, checked


def submit_passed_factors(client: WQBPrecisionClient,
                          passed_factors: List[dict],
                          submit_interval: int = 10) -> int:
    """
    正式提交通过所有检查的因子
    返回成功提交的数量
    """
    if not passed_factors:
        print("\n[正式提交] 无通过所有检查的因子")
        return 0

    print(f"\n=== 正式提交 {len(passed_factors)} 个因子 ===")
    success_count = 0

    for i, item in enumerate(passed_factors):
        f = item["factor"]
        alpha_id = f.get("alpha_id")
        name = item["factor_name"]

        # 检查是否已提交
        if f.get("submitted_to_live") == "YES":
            print(f"  [已提交] {name}")
            success_count += 1
            item["submitted"] = True
            item["submit_message"] = "已提交过"
            continue

        try:
            print(f"  [{i+1}/{len(passed_factors)}] 提交 {name} (alpha={alpha_id})")
            result = client.confirm_submit(alpha_id)

            # 标记已提交
            checked_at = item.get("checked_at")
            if checked_at:
                client.mark_submitted(alpha_id, checked_at, json.dumps(result))

            # 更新 alphas 表
            expr_settings = json.loads(f["settings_json"]) if f.get("settings_json") else DEFAULT_SETTINGS
            client.update_alpha_submit_status(
                f["expression"], expr_settings,
                "SUBMITTED", item.get("checks", {}),
                submitted_to_live=True
            )

            success_count += 1
            item["submitted"] = True
            item["submit_message"] = f"正式提交成功 (status={result.get('status', 'unknown')})"
            print(f"    ✓ {item['submit_message']}")

            if i < len(passed_factors) - 1:
                time.sleep(submit_interval)

        except Exception as e:
            print(f"    ✗ 提交失败: {e}")
            item["submit_error"] = str(e)

    print(f"\n[完成] 成功正式提交 {success_count}/{len(passed_factors)} 个因子")
    return success_count


# ============================================================
# 报告生成
# ============================================================

def generate_report(client: WQBPrecisionClient,
                    factor_names: List[str],
                    checked_factors: List[dict],
                    passed_factors: List[dict],
                    submitted_factors: List[dict],
                    report_path: str) -> str:
    """
    生成精准突破因子分析报告
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 获取所有目标因子的回测结果
    all_factors = client.get_target_factors(factor_names)
    factor_map = {f["factor_name"]: f for f in all_factors}

    # 统计
    completed = [f for f in all_factors if f.get("status") == "COMPLETED"]
    pending = [f for f in all_factors if f.get("status") == "PENDING"]
    failed = [f for f in all_factors if f.get("status") == "FAILED"]

    qualified = [f for f in completed
                 if f.get("sharpe", 0) and f.get("fitness", 0)
                 and f["sharpe"] >= 1.25 and f["fitness"] >= 1.0]

    # 检查结果映射
    check_map = {c["factor_name"]: c for c in checked_factors}

    lines = []
    lines.append("# WQB 精准突破因子分析报告")
    lines.append("")
    lines.append(f"**生成时间：** {now}")
    lines.append("")
    lines.append("## 一、策略概述")
    lines.append("")
    lines.append("**核心策略**：用更快的衰减(d5/d3)降低自相关性，同时用少量短周期波动率权重补充Fitness，")
    lines.append("精准卡在 `SELF_CORRELATION ≤ 0.7` 且 `Fitness ≥ 1.0` 的交集区域。")
    lines.append("")
    lines.append("**设计思路**：")
    lines.append("- 基线：alpha_021（隔夜-日内收益差）是已知强因子，但衰减慢导致自相关性高")
    lines.append("- 降低自相关：用 d3/d5 短衰减替代默认 d15，牺牲部分 Sharpe 换取自相关性下降")
    lines.append("- 补充 Fitness：混入少量负向波动率暴露（低波溢价），在不过度拉高自相关的前提下提升 Fitness")
    lines.append("- 条件过滤：仅在极端日/放量日下注，提升信号集中度和 Fitness")
    lines.append("")

    # 批次概览
    lines.append("## 二、批次概览")
    lines.append("")
    lines.append(f"- **计划因子数：** {len(factor_names)} 个")
    lines.append(f"- **已完成回测：** {len(completed)} 个")
    lines.append(f"- **进行中：** {len(pending)} 个")
    lines.append(f"- **失败：** {len(failed)} 个")
    lines.append(f"- **达标 (Sharpe≥1.25 & Fitness≥1.0)：** {len(qualified)} 个")
    lines.append(f"- **通过全部 8 项检查：** {len(passed_factors)} 个")
    lines.append(f"- **正式提交成功：** {len(submitted_factors)} 个")
    lines.append("")

    # 分组表现
    lines.append("## 三、分组表现")
    lines.append("")

    for group_name, group_factors in FACTOR_GROUPS.items():
        group_completed = [factor_map[n] for n in group_factors
                           if n in factor_map and factor_map[n].get("status") == "COMPLETED"]

        if not group_completed:
            lines.append(f"### {group_name}")
            lines.append("")
            lines.append(f"- 状态：暂无完成数据")
            lines.append("")
            continue

        avg_sharpe = sum(f.get("sharpe", 0) or 0 for f in group_completed) / len(group_completed)
        avg_fitness = sum(f.get("fitness", 0) or 0 for f in group_completed) / len(group_completed)
        avg_turnover = sum(f.get("turnover", 0) or 0 for f in group_completed) / len(group_completed)

        best = max(group_completed, key=lambda x: x.get("sharpe", 0) or 0)
        best_fitness = max(group_completed, key=lambda x: x.get("fitness", 0) or 0)

        lines.append(f"### {group_name}")
        lines.append("")
        lines.append(f"- 已完成：{len(group_completed)}/{len(group_factors)} 个")
        lines.append(f"- 平均 Sharpe：{avg_sharpe:.3f}")
        lines.append(f"- 平均 Fitness：{avg_fitness:.3f}")
        lines.append(f"- 平均换手率：{avg_turnover:.4f}" if avg_turnover else "- 平均换手率：N/A")
        lines.append(f"- 最高 Sharpe：{best['factor_name']} ({best.get('sharpe', 'N/A')})")
        lines.append(f"- 最高 Fitness：{best_fitness['factor_name']} ({best_fitness.get('fitness', 'N/A')})")
        lines.append("")

    # 因子详细结果表
    lines.append("## 四、因子详细回测结果")
    lines.append("")
    lines.append("| 因子名称 | 组别 | Sharpe | Fitness | 换手率 | 年化收益 | 最大回撤 | 状态 |")
    lines.append("|---------|------|--------|---------|--------|----------|----------|------|")

    # 按分组顺序排列
    category_names = {
        "baseline_d5": "组1-d5基线",
        "baseline_d3": "组1-d3基线",
        "baseline_raw": "组1-原始",
        "combo_d5_vol": "组2-d5+vol",
        "combo_d3_vol": "组3-d3+vol",
        "conditional_filter": "组4-条件过滤",
    }

    for name in factor_names:
        f = factor_map.get(name)
        if not f:
            lines.append(f"| {name} | - | - | - | - | - | - | 未提交 |")
            continue

        cat = category_names.get(f.get("category", ""), f.get("category", "-"))
        status = f.get("status", "UNKNOWN")
        status_icon = {
            "COMPLETED": "✅ 完成",
            "PENDING": "⏳ 进行中",
            "FAILED": "❌ 失败",
        }.get(status, status)

        sharpe = f"{f['sharpe']:.3f}" if f.get("sharpe") is not None else "-"
        fitness = f"{f['fitness']:.3f}" if f.get("fitness") is not None else "-"
        turnover = f"{f['turnover']:.4f}" if f.get("turnover") is not None else "-"
        ann_ret = f"{f['annual_return']*100:.2f}%" if f.get("annual_return") is not None else "-"
        mdd = f"{f['max_drawdown']*100:.2f}%" if f.get("max_drawdown") is not None else "-"

        lines.append(
            f"| {name} | {cat} | {sharpe} | {fitness} | {turnover} | {ann_ret} | {mdd} | {status_icon} |"
        )

    lines.append("")

    # 提交检查结果
    lines.append("## 五、提交检查结果（8项）")
    lines.append("")

    if not checked_factors:
        lines.append("暂无因子达标进行提交检查。")
        lines.append("")
    else:
        # 汇总表
        lines.append("### 5.1 检查汇总")
        lines.append("")
        lines.append("| 因子名称 | Sharpe | Fitness | 自相关性 | 检查结果 | 正式提交 |")
        lines.append("|---------|--------|---------|----------|----------|----------|")

        for c in checked_factors:
            sc = c.get("self_correlation")
            sc_str = f"{sc:.4f}" if sc is not None else "N/A"
            status_icon = "✅ PASS" if c["overall_status"] == "PASS" else (
                "⏳ PENDING" if c["overall_status"] == "PENDING" else (
                    "⚠️ ERROR" if c["overall_status"] == "ERROR" else "❌ FAIL"
                )
            )
            submit_icon = "✅ 已提交" if c.get("submitted") else "-"
            sharpe_str = f"{c['sharpe']:.2f}" if c.get("sharpe") else "N/A"
            fitness_str = f"{c['fitness']:.2f}" if c.get("fitness") else "N/A"
            lines.append(
                f"| {c['factor_name']} | {sharpe_str} | {fitness_str} | "
                f"{sc_str} | {status_icon} | {submit_icon} |"
            )

        lines.append("")

        # 逐项检查详情
        lines.append("### 5.2 逐项检查详情")
        lines.append("")

        check_order = [
            "LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
            "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE",
            "SELF_CORRELATION", "MATCHES_COMPETITION"
        ]

        for c in checked_factors:
            lines.append(f"#### {c['factor_name']}")
            lines.append("")
            lines.append("| 检查项 | 状态 | 数值 | 阈值 |")
            lines.append("|--------|------|------|------|")

            checks = c.get("checks", {})
            for check_name in check_order:
                check = checks.get(check_name, {})
                status = check.get("status", "N/A")
                value = check.get("value")
                limit = check.get("limit")

                status_icon = "✅ PASS" if status == "PASS" else (
                    "⏳ PENDING" if status == "PENDING" else (
                        "❌ FAIL" if status == "FAIL" else status
                    )
                )
                value_str = str(value) if value is not None else "-"
                limit_str = str(limit) if limit is not None else "-"
                lines.append(f"| {check_name} | {status_icon} | {value_str} | {limit_str} |")

            lines.append("")

            if c.get("error"):
                lines.append(f"> ⚠️ 错误: {c['error']}")
                lines.append("")

    # 正式提交结果
    lines.append("## 六、正式提交结果")
    lines.append("")

    if submitted_factors:
        for sf in submitted_factors:
            lines.append(f"- ✅ **{sf['factor_name']}** ({sf['alpha_id']})")
            if sf.get("submit_message"):
                lines.append(f"  - {sf['submit_message']}")
        lines.append("")
    else:
        lines.append("本次没有因子通过全部 8 项检查，未执行正式提交。")
        lines.append("")

    # 关键发现与建议
    lines.append("## 七、关键发现与策略建议")
    lines.append("")

    # 基于实际结果生成分析
    if completed:
        # 分析衰减对自相关的影响
        d5_factors = [factor_map[n] for n in ["alpha_021_d5", "combo_d5_vol20_w9505",
                                               "combo_d5_vol20_w9010", "combo_d5_vol20_w8515",
                                               "combo_d5_vol20_w8020"]
                      if n in factor_map and factor_map[n].get("status") == "COMPLETED"]
        d3_factors = [factor_map[n] for n in ["alpha_021_d3", "combo_d3_vol20_w9010",
                                               "combo_d3_vol20_w8020", "combo_d3_vol20_w7030"]
                      if n in factor_map and factor_map[n].get("status") == "COMPLETED"]

        lines.append("### 7.1 衰减速度 vs 自相关性")
        lines.append("")
        if d5_factors and d3_factors:
            avg_d5_sharpe = sum(f.get("sharpe", 0) or 0 for f in d5_factors) / len(d5_factors)
            avg_d3_sharpe = sum(f.get("sharpe", 0) or 0 for f in d3_factors) / len(d3_factors)
            lines.append(f"- d5 组平均 Sharpe: {avg_d5_sharpe:.3f}")
            lines.append(f"- d3 组平均 Sharpe: {avg_d3_sharpe:.3f}")
            lines.append(f"- 衰减加快 Sharpe 变化: {(avg_d3_sharpe - avg_d5_sharpe)/avg_d5_sharpe*100:+.1f}%")
            lines.append("")

        # 波动率权重分析
        lines.append("### 7.2 波动率权重对 Fitness 的影响")
        lines.append("")
        d5_vol_factors = [factor_map[n] for n in ["alpha_021_d5", "combo_d5_vol20_w9505",
                                                   "combo_d5_vol20_w9010", "combo_d5_vol20_w8515",
                                                   "combo_d5_vol20_w8020"]
                          if n in factor_map and factor_map[n].get("status") == "COMPLETED"]
        if len(d5_vol_factors) >= 2:
            d5_vol_factors_sorted = sorted(d5_vol_factors, key=lambda x: x.get("fitness", 0) or 0)
            best_fit = max(d5_vol_factors, key=lambda x: x.get("fitness", 0) or 0)
            lines.append(f"- Fitness 最高的 d5+vol 组合: **{best_fit['factor_name']}** "
                         f"(Fitness={best_fit.get('fitness', 'N/A')})")
            lines.append(f"- 对应 Sharpe: {best_fit.get('sharpe', 'N/A')}")
            lines.append("")

        # 检查自相关性达标情况
        sc_checked = [c for c in checked_factors if c.get("self_correlation") is not None]
        if sc_checked:
            lines.append("### 7.3 自相关性达标分析")
            lines.append("")
            passed_sc = [c for c in sc_checked if c["self_correlation"] <= 0.7]
            failed_sc = [c for c in sc_checked if c["self_correlation"] > 0.7]
            lines.append(f"- 自相关 ≤ 0.7 的因子: {len(passed_sc)} 个")
            lines.append(f"- 自相关 > 0.7 的因子: {len(failed_sc)} 个")
            if failed_sc:
                lines.append("- 未达标因子:")
                for c in failed_sc:
                    lines.append(f"  - {c['factor_name']}: {c['self_correlation']:.4f}")
            lines.append("")

    # 配置说明
    lines.append("## 八、配置说明")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("|------|-----|")
    lines.append("| 市场 | USA |")
    lines.append("| 股票池 | TOP3000 |")
    lines.append("| 延迟 | 1 |")
    lines.append("| 衰减 | 15（默认，因子内用ts_decay_linear覆盖） |")
    lines.append("| 中性化 | SUBINDUSTRY |")
    lines.append("| 截断 | 0.08 |")
    lines.append("| 巴氏消毒 | ON |")
    lines.append("| 回测周期 | P1Y6M (1年6个月) |")
    lines.append("| 表达式语言 | FASTEXPR |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间: {now}*")

    # 写入文件
    report_content = "\n".join(lines)
    abs_path = os.path.abspath(report_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return abs_path


# ============================================================
# 主函数
# ============================================================

async def main():
    # 参数解析
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    email = sys.argv[2] if len(sys.argv) > 2 else "q1z2q3@126.com"
    password = sys.argv[3] if len(sys.argv) > 3 else "W2025zq0118"
    db_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    submit_interval = int(sys.argv[5]) if len(sys.argv) > 5 else 50
    min_sharpe = float(sys.argv[6]) if len(sys.argv) > 6 else 1.25
    min_fitness = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0
    report_path = sys.argv[8] if len(sys.argv) > 8 else os.path.join(OUTPUT_DIR, "wqb_precision_breakthrough_report.md")
    skip_submit = (sys.argv[9].lower() == "true") if len(sys.argv) > 9 else False

    factor_names = [f[0] for f in FACTOR_LIST]

    print(f"[参数] result_mode={result_mode}")
    print(f"[参数] 因子数量: {len(factor_names)}")
    print(f"[参数] 提交间隔: {submit_interval}s")
    print(f"[参数] 状态库: {db_path}")
    print(f"[参数] 达标阈值: Sharpe≥{min_sharpe}, Fitness≥{min_fitness}")
    print(f"[参数] 报告路径: {report_path}")
    print(f"[参数] 仅检查不提交: {skip_submit}")

    # 映射 result_mode
    actual_mode = result_mode if result_mode != "auto" else "display_only"

    # 延迟导入 codeact_sdk
    try:
        from codeact_sdk import CodeActSDK
        sdk = CodeActSDK()
    except ImportError:
        sdk = None
        print("[警告] codeact_sdk 不可用，仅本地运行模式")

    try:
        # 1. 初始化客户端和数据库
        print("\n=== 步骤1: 初始化 ===")
        client = WQBPrecisionClient(email, password, db_path)
        client._ensure_tables()

        # 2. 登录
        print("\n=== 步骤2: 登录 WQB ===")
        client.authenticate()

        # 3. 先处理已有的 PENDING 因子
        print("\n=== 步骤3: 处理已有 PENDING 因子 ===")
        wait_for_results(client, poll_interval=15, max_polls=10)

        # 4. 提交新因子
        if not skip_submit:
            print("\n=== 步骤4: 提交新因子 ===")
            submit_new_factors(client, FACTOR_LIST, submit_interval=submit_interval)

            # 5. 等待回测完成
            print("\n=== 步骤5: 等待回测完成 ===")
            wait_for_results(client, poll_interval=15, max_polls=30)
        else:
            print("\n=== 步骤4-5: 跳过提交，直接使用已有结果 ===")

        # 6. 运行提交检查
        print("\n=== 步骤6: 提交检查 ===")
        passed_factors, checked_factors = run_submit_checks(
            client, factor_names,
            min_sharpe=min_sharpe,
            min_fitness=min_fitness,
            check_interval=submit_interval,
        )

        # 7. 正式提交通过的因子
        submitted_factors = []
        if passed_factors:
            print("\n=== 步骤7: 正式提交 ===")
            success_count = submit_passed_factors(client, passed_factors)
            submitted_factors = [p for p in passed_factors if p.get("submitted")]

        # 8. 生成报告
        print("\n=== 步骤8: 生成报告 ===")
        abs_report_path = generate_report(
            client, factor_names, checked_factors,
            passed_factors, submitted_factors, report_path
        )
        print(f"报告已生成: {abs_report_path}")

        # 9. 构造用户摘要
        all_target = client.get_target_factors(factor_names)
        completed_count = sum(1 for f in all_target if f.get("status") == "COMPLETED")
        pass_check_count = len(passed_factors)
        submitted_count = len(submitted_factors)

        summary_lines = []
        summary_lines.append(f"**WQB 精准突破因子结果** | {len(factor_names)} 个因子")
        summary_lines.append("")
        summary_lines.append(
            f"✅ 回测完成: {completed_count}/{len(factor_names)} | "
            f"📊 达标待查: {len(checked_factors)} | "
            f"🎯 通过8项: {pass_check_count} | "
            f"📤 已提交: {submitted_count}"
        )
        summary_lines.append("")

        # 列出关键因子结果
        if checked_factors:
            summary_lines.append("**提交检查关键结果：**")
            for c in checked_factors[:8]:  # 最多显示8个
                sc = c.get("self_correlation")
                sc_str = f"自相关={sc:.3f}" if sc is not None else ""
                status_str = "✅ PASS" if c["overall_status"] == "PASS" else (
                    "❌ FAIL" if c["overall_status"] == "FAIL" else (
                        "⚠️ ERROR" if c["overall_status"] == "ERROR" else "⏳ PENDING"
                    )
                )
                submit_tag = " [已提交]" if c.get("submitted") else ""
                sharpe_str = f"Sharpe={c.get('sharpe', 'N/A')}"
                fit_str = f"Fit={c.get('fitness', 'N/A')}"
                summary_lines.append(
                    f"- {c['factor_name']}: {status_str} ({sharpe_str}, {fit_str}, {sc_str}){submit_tag}"
                )
        else:
            # 显示回测结果概要
            completed_factors = [f for f in all_target if f.get("status") == "COMPLETED"]
            if completed_factors:
                summary_lines.append("**回测结果概要：**")
                for f in sorted(completed_factors, key=lambda x: x.get("sharpe", 0) or 0, reverse=True)[:8]:
                    sharpe = f.get("sharpe", 0) or 0
                    fitness = f.get("fitness", 0) or 0
                    tag = " ⭐达标" if sharpe >= min_sharpe and fitness >= min_fitness else ""
                    summary_lines.append(
                        f"- {f['factor_name']}: Sharpe={sharpe:.3f}, Fitness={fitness:.3f}{tag}"
                    )

        summary_lines.append("")
        summary_lines.append(f"详细报告: [wqb_precision_breakthrough_report.md](computer://{abs_report_path})")

        message = "\n".join(summary_lines)

        # 提交结果
        if sdk:
            await sdk.submit_result(
                result_mode=actual_mode,
                status="success",
                message=message,
                data={
                    "report_path": report_path,
                    "total_factors": len(factor_names),
                    "completed_count": completed_count,
                    "checked_count": len(checked_factors),
                    "pass_check_count": pass_check_count,
                    "submitted_count": submitted_count,
                    "submitted_factors": [
                        {"factor_name": sf["factor_name"], "alpha_id": sf["alpha_id"]}
                        for sf in submitted_factors
                    ],
                    "factor_groups": {k: v for k, v in FACTOR_GROUPS.items()},
                },
            )
        else:
            print("\n=== 最终结果 ===")
            print(message)

    except Exception as e:
        error_msg = f"执行失败: {type(e).__name__}: {e}"
        print(f"\n❌ {error_msg}")
        import traceback
        traceback.print_exc()

        if sdk:
            await sdk.submit_result(
                result_mode="notify",
                status="error",
                message=error_msg,
                data={"error_type": type(e).__name__},
            )
        else:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
