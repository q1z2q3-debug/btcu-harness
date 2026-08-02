#!/usr/bin/env python3
"""
WQB 批量因子提交与提交检查脚本
=================================

功能：
  1. 批量提交因子到 WQB 平台回测
  2. 自动去重（基于表达式+设置哈希）
  3. 等待回测结果
  4. 筛选 Sharpe≥1.25 且 Fitness≥1.0 的因子
  5. 对达标因子做提交检查（8项检查）
  6. 对通过所有检查的因子正式提交
  7. 生成跃迁因子报告

支持断点续跑：每次运行先处理 PENDING 状态的因子，再提交新因子。
"""

import asyncio
import json
import os
import sys
import time
import sqlite3
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

DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")
REPORT_PATH = os.path.join(OUTPUT_DIR, "wqb_breakthrough_report.md")
BACKTEST_REPORT_PATH = os.path.join(OUTPUT_DIR, "wqb_backtest_report.md")

# ============================================================
# 因子列表（28个）
# ============================================================

FACTOR_LIST = [
    # (name, category, expression)
    ("mom_accel_5d2d", "breakthrough", "rank(ts_delta(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), 2))"),
    ("mom_accel_10d5d", "breakthrough", "rank(ts_delta(divide(subtract(close, ts_delay(close, 10)), ts_delay(close, 10)), 5))"),
    ("vol_accel_5d3d", "breakthrough", "rank(ts_delta(ts_mean(volume, 5), 3))"),
    ("price_vol_accel", "breakthrough", "rank(multiply(ts_delta(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5)), 2), ts_delta(ts_rank(volume, 20), 2)))"),
    ("vol_decrease_rate", "breakthrough", "rank(-ts_delta(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), 5))"),
    ("gap_reversal_extreme", "conditional", "rank(if_else(greater(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 0.03), -1, if_else(less(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), -0.03), 1, 0)))"),
    ("volume_spike_reversal", "conditional", "rank(if_else(greater(volume, multiply(2, ts_mean(volume, 20))), multiply(-1, divide(subtract(close, open), open)), 0))"),
    ("vol_breakout_reversal", "conditional", "rank(if_else(greater(ts_std_dev(log(divide(close, ts_delay(close, 1))), 10), multiply(1.5, ts_std_dev(log(divide(close, ts_delay(close, 1))), 60))), -divide(subtract(close, open), open), 0))"),
    ("extreme_day_reversal", "conditional", "rank(multiply(ts_rank(abs(divide(subtract(close, ts_delay(close, 1)), ts_delay(close, 1))), 20), -divide(subtract(close, ts_delay(close, 1)), ts_delay(close, 1))))"),
    ("high_vol_reversal", "conditional", "rank(trade_when(-divide(subtract(close, ts_delay(close, 1)), ts_delay(close, 1)), greater(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), multiply(1.2, ts_std_dev(log(divide(close, ts_delay(close, 1))), 120))), 0))"),
    ("rank_momentum_5d", "rank_change", "rank(ts_delta(rank(close), 5))"),
    ("rank_accel_5d3d", "rank_change", "rank(ts_delta(ts_delta(rank(close), 5), 3))"),
    ("volume_rank_change", "rank_change", "rank(ts_delta(rank(volume), 3))"),
    ("return_rank_momentum", "rank_change", "rank(ts_delta(rank(divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5))), 3))"),
    ("mom_x_volume_rank", "nonlinear", "rank(multiply(divide(subtract(close, ts_delay(close, 10)), ts_delay(close, 10)), ts_rank(volume, 20)))"),
    ("mom_div_vol", "nonlinear", "rank(divide(divide(subtract(close, ts_delay(close, 10)), ts_delay(close, 10)), add(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), 0.001)))"),
    ("long_mom_short_vol", "nonlinear", "rank(subtract(divide(subtract(close, ts_delay(close, 10)), ts_delay(close, 10)), ts_std_dev(log(divide(close, ts_delay(close, 1))), 20)))"),
    ("vol_drop_mom", "nonlinear", "rank(multiply(-ts_delta(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), 5), divide(subtract(close, ts_delay(close, 5)), ts_delay(close, 5))))"),
    ("overnight_change_rate", "overnight_intraday", "rank(ts_delta(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 3))"),
    ("intraday_change_rate", "overnight_intraday", "rank(ts_delta(divide(subtract(close, open), open), 3))"),
    ("oi_divergence_change", "overnight_intraday", "rank(ts_delta(subtract(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), divide(subtract(close, open), open)), 3))"),
    ("overnight_momentum", "overnight_intraday", "rank(multiply(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), ts_rank(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 10)))"),
    ("oi_combo_change", "overnight_intraday", "rank(subtract(ts_delta(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), 3), ts_delta(divide(subtract(close, open), open), 3)))"),
    ("vpd_change_5d", "vpd", "rank(ts_delta(subtract(rank(volume), rank(abs(divide(subtract(close, ts_delay(close, 1)), ts_delay(close, 1))))), 5))"),
    ("vpd_accel", "vpd", "rank(ts_delta(ts_delta(subtract(rank(volume), rank(abs(divide(subtract(close, ts_delay(close, 1)), ts_delay(close, 1))))), 3), 2))"),
    ("gap_with_volume", "hybrid", "rank(multiply(divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), ts_delta(ts_rank(volume, 20), 1)))"),
    ("intraday_vol_change", "hybrid", "rank(multiply(divide(subtract(close, open), open), -ts_delta(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), 5)))"),
    ("rank_vol_sync", "hybrid", "rank(multiply(ts_delta(rank(close), 3), ts_delta(rank(volume), 3)))"),
]

# ============================================================
# 基准提交设置
# ============================================================

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

BASE_URL = "https://api.worldquantbrain.com"

# 提交检查项及阈值
SUBMISSION_CHECKS = {
    "LOW_SHARPE": 1.25,
    "LOW_FITNESS": 1.0,
    "LOW_TURNOVER": 0.01,
    "HIGH_TURNOVER": 0.7,
    "CONCENTRATED_WEIGHT": None,  # 无数值阈值，PASS/FAIL
    "LOW_SUB_UNIVERSE_SHARPE": None,
    "SELF_CORRELATION": 0.7,
    "MATCHES_COMPETITION": None,
}


# ============================================================
# WQB 增强 API 客户端
# ============================================================

class WQBEnhancedClient:
    """增强版 WQB 客户端，添加提交检查功能"""

    def __init__(self, email: str, password: str, db_path: str = DB_PATH):
        # 清除代理环境变量，避免代理问题
        for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
            if var in os.environ:
                del os.environ[var]

        self.email = email
        self._session = requests.Session()
        self._session.auth = (email, password)
        self._session.trust_env = False  # 禁用代理
        self._authenticated = False
        self.db_path = db_path

    def authenticate(self) -> dict:
        """登录认证"""
        response = self._session.post(f"{BASE_URL}/authentication")
        response.raise_for_status()
        self._authenticated = True
        user_info = response.json()
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

        response = self._session.post(f"{BASE_URL}/simulations", json=payload)
        response.raise_for_status()
        return response.headers.get("Location")

    def poll_simulation(self, progress_url: str) -> Tuple[str, Optional[str]]:
        """
        轮询模拟进度
        Returns: (status, alpha_id)
          status: "PENDING" | "COMPLETED" | "FAILED"
        """
        try:
            response = self._session.get(progress_url)
            retry_after = float(response.headers.get("Retry-After", 0))

            if retry_after == 0:
                response.raise_for_status()
                result = response.json()
                alpha_id = result.get("alpha")
                return "COMPLETED", alpha_id
            else:
                return "PENDING", None
        except Exception as e:
            return "FAILED", None

    def get_alpha(self, alpha_id: str) -> dict:
        """获取 Alpha 详情"""
        response = self._session.get(f"{BASE_URL}/alphas/{alpha_id}")
        response.raise_for_status()
        return response.json()

    # ---- 提交检查 ----

    def run_submit_check(self, alpha_id: str) -> dict:
        """
        运行提交检查（POST /alphas/{id}/submit）
        
        注意：即使返回403，响应体中也包含检查结果。
        检查结果在 is.checks 数组中。
        
        Returns:
            dict with:
              - status: "PASS" | "FAIL" | "PENDING"
              - checks: {check_name: {status, value, limit}}
              - raw: 原始响应数据
        """
        try:
            response = self._session.post(f"{BASE_URL}/alphas/{alpha_id}/submit")
            # 403是正常的（检查未通过），200/201是全部通过
            if response.status_code in (403, 200, 201, 202):
                try:
                    data = response.json()
                except:
                    data = {}
            else:
                response.raise_for_status()
                data = response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                try:
                    data = e.response.json()
                except:
                    data = {}
            else:
                raise

        # 解析检查结果
        is_data = data.get("is", {})
        checks_list = is_data.get("checks", [])
        checks_dict = {}
        all_pass = True
        has_pending = False

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
            if result == "FAIL":
                all_pass = False
            elif result == "PENDING":
                has_pending = True

        if has_pending:
            overall_status = "PENDING"
        elif all_pass:
            overall_status = "PASS"
        else:
            overall_status = "FAIL"

        return {
            "status": overall_status,
            "checks": checks_dict,
            "raw": data,
        }

    def confirm_submit(self, alpha_id: str) -> dict:
        """
        正式提交 Alpha（通过所有检查后）
        PUT /alphas/{id}/submit
        """
        response = self._session.put(f"{BASE_URL}/alphas/{alpha_id}/submit")
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
        import hashlib
        key = json.dumps({"expr": expression, "settings": settings}, sort_keys=True)
        return hashlib.md5(key.encode()).hexdigest()

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
                        factor_name = ?, category = ?, submitted_at = ?
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
                json.dumps(metrics.get("is_summary", {})),
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

    def save_submit_check(self, expression: str, settings: dict,
                          check_result: dict):
        """保存提交检查结果"""
        expr_hash = self._expr_hash(expression, settings)
        with self._db_conn() as conn:
            # 确保有 submit_checks 列
            try:
                conn.execute("ALTER TABLE alphas ADD COLUMN submit_checks TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE alphas ADD COLUMN submit_status TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE alphas ADD COLUMN submitted_to_live TEXT")
            except sqlite3.OperationalError:
                pass

            conn.execute("""
                UPDATE alphas SET submit_checks = ?, submit_status = ?
                WHERE expr_hash = ?
            """, (
                json.dumps(check_result.get("checks", {})),
                check_result.get("status", "UNKNOWN"),
                expr_hash
            ))

    def mark_submitted(self, expression: str, settings: dict):
        """标记因子已正式提交"""
        expr_hash = self._expr_hash(expression, settings)
        with self._db_conn() as conn:
            conn.execute("""
                UPDATE alphas SET submitted_to_live = 'YES' WHERE expr_hash = ?
            """, (expr_hash,))

    def list_all_factors_with_names(self) -> List[dict]:
        """列出所有带名字的因子"""
        with self._db_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM alphas
                WHERE factor_name IS NOT NULL
                ORDER BY sharpe DESC
            """).fetchall()
            return [dict(row) for row in rows]


# ============================================================
# 核心流程
# ============================================================

def login_and_init(email: str, password: str) -> WQBEnhancedClient:
    """登录并初始化客户端"""
    client = WQBEnhancedClient(email, password)
    client.authenticate()
    return client


def retry_with_backoff(func, *args, max_retries=5, base_delay=3.0, **kwargs):
    """指数退避重试"""
    delay = base_delay
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response.status_code in (429, 500, 502, 503, 504):
                last_exception = e
                retry_after = e.response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else delay * (2 ** attempt)
                print(f"  [重试 {attempt+1}/{max_retries}] 状态码 {e.response.status_code}, 等待 {wait:.1f}s")
                time.sleep(wait)
            else:
                raise
    raise last_exception


def process_pending_factors(client: WQBEnhancedClient, poll_interval: int = 10) -> int:
    """
    处理 PENDING 状态的因子（等待它们完成）
    返回完成的数量
    """
    pending = client.get_pending_factors()
    if not pending:
        print("[状态] 无待处理的 PENDING 因子")
        return 0

    print(f"[状态] 发现 {len(pending)} 个 PENDING 因子，开始等待结果...")
    completed_count = 0
    max_polls = 12  # 最多轮询12次（约2分钟），避免超时

    for poll_round in range(max_polls):
        all_done = True
        for factor in pending:
            if factor["status"] != "PENDING":
                continue
            if not factor.get("progress_url"):
                continue

            try:
                status, alpha_id = retry_with_backoff(
                    client.poll_simulation, factor["progress_url"]
                )

                if status == "COMPLETED" and alpha_id:
                    print(f"  ✓ {factor.get('factor_name', factor['expr_hash'][:8])}: 完成, Alpha ID={alpha_id}")
                    # 获取详细指标
                    alpha_data = retry_with_backoff(client.get_alpha, alpha_id)
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
                    factor["status"] = "COMPLETED"
                    completed_count += 1
                elif status == "FAILED":
                    print(f"  ✗ {factor.get('factor_name', factor['expr_hash'][:8])}: 失败")
                    settings = json.loads(factor["settings_json"])
                    client.save_factor_failed(
                        factor["expression"], settings, "poll failed"
                    )
                    factor["status"] = "FAILED"
                else:
                    all_done = False
            except Exception as e:
                print(f"  [错误] {factor.get('factor_name', factor['expr_hash'][:8])}: {e}")
                all_done = False

        if all_done:
            break

        if poll_round < max_polls - 1:
            pending_count = sum(1 for f in pending if f["status"] == "PENDING")
            print(f"  [第 {poll_round+1} 轮] 还有 {pending_count} 个因子等待中...")
            time.sleep(poll_interval)

    print(f"[完成] 本轮完成 {completed_count} 个因子的回测")
    return completed_count


def submit_new_factors(client: WQBEnhancedClient,
                       factors: List[tuple],
                       submit_interval: int = 40,
                       max_submit: int = 10) -> int:
    """
    提交新因子
    Args:
      factors: (name, category, expression) 列表
      submit_interval: 提交间隔秒数
      max_submit: 本次最多提交数量（防止超时）
    Returns: 新提交的数量
    """
    submitted = 0
    settings = DEFAULT_SETTINGS

    for i, (name, category, expression) in enumerate(factors):
        if submitted >= max_submit:
            print(f"[限制] 已达到本次最大提交数 {max_submit}，停止提交")
            break

        # 检查是否已存在
        existing = client.get_factor_status(expression, settings)
        if existing:
            status = existing.get("status", "UNKNOWN")
            if status in ("COMPLETED", "PENDING"):
                print(f"  [跳过] {name}: 已存在 (status={status})")
                # 更新名字和分类（如果之前没有）
                if not existing.get("factor_name"):
                    with client._db_conn() as conn:
                        expr_hash = client._expr_hash(expression, settings)
                        conn.execute("""
                            UPDATE alphas SET factor_name = ?, category = ?
                            WHERE expr_hash = ?
                        """, (name, category, expr_hash))
                continue
            elif status == "FAILED":
                print(f"  [重试] {name}: 之前失败，重新提交")
            else:
                print(f"  [跳过] {name}: 状态={status}")
                continue

        print(f"  [提交 {submitted+1}] {name} ({category})")
        try:
            progress_url = retry_with_backoff(
                client.submit_simulation, expression, settings
            )
            client.save_factor_submitted(expression, settings, name, category, progress_url)
            submitted += 1
            print(f"    → 提交成功: {progress_url}")
        except Exception as e:
            print(f"    ✗ 提交失败: {e}")
            client.save_factor_failed(expression, settings, f"submit failed: {e}")

        # 提交间隔
        if submitted < max_submit and i < len(factors) - 1:
            print(f"    等待 {submit_interval}s 避免限流...")
            time.sleep(submit_interval)

    return submitted


def get_metrics_from_alpha(alpha_data: dict) -> dict:
    """从 Alpha 数据提取核心指标"""
    is_data = alpha_data.get("is", {})
    return {
        "sharpe": is_data.get("sharpe"),
        "fitness": is_data.get("fitness"),
        "turnover": is_data.get("turnover"),
        "annual_return": is_data.get("returns"),
        "max_drawdown": is_data.get("drawdown"),
        "is_summary": is_data,
    }


def run_submit_checks(client: WQBEnhancedClient,
                      min_sharpe: float = 1.25,
                      min_fitness: float = 1.0,
                      factor_list: List[tuple] = None) -> Tuple[List[dict], List[dict]]:
    """
    对达标因子运行提交检查
    
    Args:
      factor_list: 只检查指定列表中的因子（None则检查所有）
    Returns: (passed_factors, all_checked_factors)
    """
    settings = DEFAULT_SETTINGS

    # 获取目标因子
    if factor_list:
        target_names = {f[0] for f in factor_list}
        all_factors = [
            f for f in client.list_all_factors_with_names()
            if f.get("factor_name") in target_names
        ]
    else:
        all_factors = client.list_all_factors_with_names()

    # 筛选达标因子
    qualified = []
    for f in all_factors:
        sharpe = f.get("sharpe")
        fitness = f.get("fitness")
        if (sharpe is not None and sharpe >= min_sharpe
                and fitness is not None and fitness >= min_fitness):
            qualified.append(f)

    print(f"\n[筛选] Sharpe≥{min_sharpe} 且 Fitness≥{min_fitness} 的因子: {len(qualified)} 个")
    for f in qualified:
        print(f"  - {f['factor_name']}: Sharpe={f['sharpe']:.2f}, Fitness={f['fitness']:.2f}")

    if not qualified:
        print("  没有达标因子，跳过提交检查")
        return [], []

    # 对每个达标因子做提交检查
    passed = []
    checked = []

    for f in qualified:
        alpha_id = f.get("alpha_id")
        if not alpha_id:
            print(f"  [跳过] {f['factor_name']}: 无 alpha_id")
            continue

        name = f["factor_name"]
        print(f"\n  [检查] {name} (alpha={alpha_id})")

        try:
            # 运行提交检查
            check_result = retry_with_backoff(client.run_submit_check, alpha_id)

            # 如果有PENDING的检查项，等待一下再查
            if check_result["status"] == "PENDING":
                print(f"    部分检查进行中，等待后重试...")
                for i in range(6):
                    time.sleep(10)
                    check_result = retry_with_backoff(client.run_submit_check, alpha_id)
                    if check_result["status"] != "PENDING":
                        break
                    print(f"    仍在进行中... ({i+1}/6)")

            checks = check_result["checks"]
            all_pass = check_result["status"] == "PASS"

            # 输出检查详情
            for check_name, check_info in checks.items():
                check_status = check_info.get("status", "UNKNOWN")
                check_value = check_info.get("value")
                check_limit = check_info.get("limit")
                status_icon = "✓" if check_status == "PASS" else "✗" if check_status == "FAIL" else "⏳"
                val_str = f"={check_value:.4f}" if isinstance(check_value, (int, float)) else f"={check_value}" if check_value else ""
                lim_str = f" (limit={check_limit})" if check_limit else ""
                print(f"    {status_icon} {check_name}: {check_status}{val_str}{lim_str}")

            result = {
                "factor": f,
                "checks": checks,
                "all_pass": all_pass,
                "overall_status": check_result["status"],
            }
            checked.append(result)

            # 保存检查结果
            expr_settings = json.loads(f["settings_json"]) if f.get("settings_json") else settings
            client.save_submit_check(f["expression"], expr_settings, {
                "checks": checks,
                "status": check_result["status"],
            })

            if all_pass:
                passed.append(result)
                print(f"    ★ 全部通过！可以正式提交")

        except Exception as e:
            print(f"    ✗ 检查失败: {e}")
            import traceback
            traceback.print_exc()

    return passed, checked


def submit_passed_factors(client: WQBEnhancedClient, passed_factors: List[dict]) -> int:
    """
    正式提交通过所有检查的因子
    返回成功提交的数量
    """
    if not passed_factors:
        return 0

    print(f"\n[正式提交] {len(passed_factors)} 个因子通过所有检查，开始正式提交...")
    success_count = 0

    for item in passed_factors:
        f = item["factor"]
        alpha_id = f.get("alpha_id")
        name = f["factor_name"]

        # 检查是否已提交
        if f.get("submitted_to_live") == "YES":
            print(f"  [已提交] {name}")
            success_count += 1
            continue

        try:
            print(f"  [提交] {name} (alpha={alpha_id})")
            result = retry_with_backoff(client.confirm_submit, alpha_id)
            expr_settings = json.loads(f["settings_json"]) if f.get("settings_json") else DEFAULT_SETTINGS
            client.mark_submitted(f["expression"], expr_settings)
            success_count += 1
            print(f"    ✓ 提交成功")
            time.sleep(2)
        except Exception as e:
            print(f"    ✗ 提交失败: {e}")

    return success_count


def generate_report(client: WQBEnhancedClient,
                    passed_factors: List[dict],
                    checked_factors: List[dict]) -> str:
    """生成跃迁因子报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_factors = client.list_all_factors_with_names()

    # 统计本批次28个因子的情况（每个因子只取最新/最佳的一条记录）
    factor_names = [f[0] for f in FACTOR_LIST]
    factor_category_map = {f[0]: f[1] for f in FACTOR_LIST}
    
    # 去重：同一个factor_name只保留一条（Sharpe最高的）
    best_by_name = {}
    for f in all_factors:
        name = f.get("factor_name")
        if not name or name not in factor_names:
            continue
        sharpe = f.get("sharpe") or -999
        if name not in best_by_name or sharpe > (best_by_name[name].get("sharpe") or -999):
            # 确保category正确
            f = dict(f)
            f["category"] = factor_category_map.get(name, f.get("category", "unknown"))
            best_by_name[name] = f
    
    batch_factors = list(best_by_name.values())
    completed = [f for f in batch_factors if f["status"] == "COMPLETED"]
    pending = [f for f in batch_factors if f["status"] == "PENDING"]
    failed = [f for f in batch_factors if f["status"] == "FAILED"]

    # 达标因子
    qualified = [f for f in completed
                 if f.get("sharpe", 0) >= 1.25 and f.get("fitness", 0) >= 1.0]

    lines = []
    lines.append("# WQB 跃迁因子批量提交报告")
    lines.append("")
    lines.append(f"**生成时间：** {now}")
    lines.append("")
    lines.append("## 一、批次概览")
    lines.append("")
    lines.append(f"- **计划提交：** 28 个因子")
    lines.append(f"- **已完成回测：** {len(completed)} 个")
    lines.append(f"- **进行中：** {len(pending)} 个")
    lines.append(f"- **失败：** {len(failed)} 个")
    lines.append(f"- **达标 (Sharpe≥1.25 & Fitness≥1.0)：** {len(qualified)} 个")
    lines.append(f"- **通过所有提交检查：** {len(passed_factors)} 个")
    lines.append("")

    # 分类统计
    lines.append("## 二、分类表现")
    lines.append("")
    categories = {}
    for f in completed:
        cat = f.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    for cat, factors in sorted(categories.items()):
        avg_sharpe = sum(f.get("sharpe", 0) or 0 for f in factors) / len(factors) if factors else 0
        avg_fitness = sum(f.get("fitness", 0) or 0 for f in factors) / len(factors) if factors else 0
        best = max(factors, key=lambda x: x.get("sharpe", 0) or 0)
        lines.append(f"### {cat}")
        lines.append("")
        lines.append(f"- 数量：{len(factors)} 个")
        lines.append(f"- 平均 Sharpe：{avg_sharpe:.3f}")
        lines.append(f"- 平均 Fitness：{avg_fitness:.3f}")
        lines.append(f"- 最佳因子：{best['factor_name']} (Sharpe={best.get('sharpe', 'N/A')})")
        lines.append("")

    # 详细结果表
    lines.append("## 三、因子详细结果")
    lines.append("")
    lines.append("| 因子名称 | 类别 | Sharpe | Fitness | 换手率 | 年化收益 | 最大回撤 | 状态 |")
    lines.append("|---------|------|--------|---------|--------|----------|----------|------|")

    # 按 Sharpe 排序
    sorted_factors = sorted(batch_factors, key=lambda x: x.get("sharpe", -999) or -999, reverse=True)
    for f in sorted_factors:
        name = f.get("factor_name", "?")
        cat = f.get("category", "?")
        sharpe = f"{f['sharpe']:.2f}" if f.get("sharpe") is not None else "-"
        fitness = f"{f['fitness']:.2f}" if f.get("fitness") is not None else "-"
        turnover = f"{f['turnover']:.3f}" if f.get("turnover") is not None else "-"
        ann_ret = f"{f['annual_return']:.2%}" if f.get("annual_return") is not None else "-"
        mdd = f"{f['max_drawdown']:.2%}" if f.get("max_drawdown") is not None else "-"
        status = f["status"]
        # 标记达标
        if f.get("sharpe", 0) and f.get("fitness", 0) and f["sharpe"] >= 1.25 and f["fitness"] >= 1.0:
            status = "★" + status
        lines.append(f"| {name} | {cat} | {sharpe} | {fitness} | {turnover} | {ann_ret} | {mdd} | {status} |")

    lines.append("")

    # 提交检查结果
    lines.append("## 四、提交检查结果")
    lines.append("")

    if not checked_factors:
        lines.append("暂无达标因子或检查未完成。")
    else:
        check_names = list(SUBMISSION_CHECKS.keys())
        lines.append(f"共有 {len(checked_factors)} 个因子参与提交检查，{len(passed_factors)} 个通过全部检查。")
        lines.append("")
        lines.append("| 因子名称 | Sharpe | Fitness | " + " | ".join(check_names) + " | 结果 |")
        lines.append("|---------|--------|---------|" + "|".join(["---"] * len(check_names)) + "|------|")

        for item in checked_factors:
            f = item["factor"]
            name = f["factor_name"]
            sharpe = f"{f.get('sharpe', 0):.2f}"
            fitness = f"{f.get('fitness', 0):.2f}"
            check_results = []
            for cn in check_names:
                ci = item["checks"].get(cn, {})
                cs = ci.get("status", "?")
                icon = "✓" if cs == "PASS" else "✗" if cs == "FAIL" else "?"
                check_results.append(icon)
            overall = "★ 通过" if item["all_pass"] else "✗ 未通过"
            lines.append(f"| {name} | {sharpe} | {fitness} | " + " | ".join(check_results) + f" | {overall} |")

    lines.append("")

    # 达标因子表达式
    if qualified:
        lines.append("## 五、达标因子表达式")
        lines.append("")
        for f in qualified:
            lines.append(f"### {f['factor_name']} ({f.get('category', '?')})")
            lines.append("")
            lines.append(f"- **Sharpe：** {f.get('sharpe', 'N/A')}")
            lines.append(f"- **Fitness：** {f.get('fitness', 'N/A')}")
            lines.append(f"- **Alpha ID：** {f.get('alpha_id', 'N/A')}")
            lines.append(f"- **表达式：**")
            lines.append("")
            lines.append("```")
            lines.append(f.get("expression", ""))
            lines.append("```")
            lines.append("")

    # 待完成
    if pending:
        lines.append("## 六、待完成因子")
        lines.append("")
        for f in pending:
            lines.append(f"- {f.get('factor_name', '?')} ({f.get('category', '?')})")
        lines.append("")

    # 设置说明
    lines.append("## 七、回测设置")
    lines.append("")
    lines.append("| 参数 | 值 |")
    lines.append("|------|----|")
    for k, v in DEFAULT_SETTINGS.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("---")
    lines.append(f"*报告生成时间：{now}*")

    report_content = "\n".join(lines)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_content)

    # 同步更新回测报告
    update_backtest_summary_report(client)

    print(f"\n[报告] 已生成: {REPORT_PATH}")
    return REPORT_PATH


def update_backtest_summary_report(client: WQBEnhancedClient):
    """更新总回测汇总报告"""
    all_factors = client.list_all_factors_with_names()
    completed = [f for f in all_factors if f["status"] == "COMPLETED"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# WQB 因子回测汇总")
    lines.append("")
    lines.append(f"**更新时间：** {now}")
    lines.append("")
    lines.append(f"- **总因子数：** {len(all_factors)}")
    lines.append(f"- **已完成：** {len(completed)}")
    lines.append(f"- **进行中：** {sum(1 for f in all_factors if f['status'] == 'PENDING')}")
    lines.append(f"- **失败：** {sum(1 for f in all_factors if f['status'] == 'FAILED')}")
    lines.append("")

    # TOP 10
    top10 = sorted(completed, key=lambda x: x.get("sharpe", -999) or -999, reverse=True)[:10]
    lines.append("## TOP 10 因子 (按 Sharpe)")
    lines.append("")
    lines.append("| 排名 | 因子名称 | 类别 | Sharpe | Fitness | 换手率 |")
    lines.append("|------|---------|------|--------|---------|--------|")
    for i, f in enumerate(top10, 1):
        name = f.get("factor_name", f["expr_hash"][:8])
        cat = f.get("category", "-")
        sharpe = f"{f.get('sharpe', 0):.2f}"
        fitness = f"{f.get('fitness', 0):.2f}"
        turnover = f"{f.get('turnover', 0):.3f}"
        lines.append(f"| {i} | {name} | {cat} | {sharpe} | {fitness} | {turnover} |")
    lines.append("")

    with open(BACKTEST_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 主流程
# ============================================================

def main_sync(result_mode: str, max_submit_per_run: int = 10,
              submit_interval: int = 40,
              wait_after_submit: bool = True) -> dict:
    """
    同步主流程（WQB API 客户端是同步的）
    返回结果字典，供异步包装层提交
    """
    # 读取账号
    email = "q1z2q3@126.com"
    password = "W2025zq0118"

    print("=" * 60)
    print("WQB 批量因子提交与检查")
    print("=" * 60)
    print(f"参数: max_submit_per_run={max_submit_per_run}, submit_interval={submit_interval}s")
    print()

    # 1. 登录
    print("[步骤1] 登录 WQB 平台...")
    client = login_and_init(email, password)
    print()

    # 2. 先处理 PENDING 因子
    print("[步骤2] 处理进行中的因子...")
    completed_pending = process_pending_factors(client, poll_interval=10)
    print()

    # 3. 提交新因子
    print("[步骤3] 提交新因子...")
    new_submitted = submit_new_factors(
        client, FACTOR_LIST,
        submit_interval=submit_interval,
        max_submit=max_submit_per_run
    )
    print(f"  本次新提交: {new_submitted} 个")
    print()

    # 4. 等待新提交的因子完成（可选）
    if new_submitted > 0 and wait_after_submit:
        print("[步骤4] 等待新提交因子完成...")
        completed_new = process_pending_factors(client, poll_interval=10)
        print(f"  新完成: {completed_new} 个")
        print()
    elif new_submitted > 0:
        print("[步骤4] 已提交新因子，等待将在下一轮进行（wait_after_submit=False）")
        print()

    # 5. 检查是否所有28个因子都完成了
    settings = DEFAULT_SETTINGS
    all_done = True
    for name, category, expression in FACTOR_LIST:
        status = client.get_factor_status(expression, settings)
        if not status or status.get("status") == "PENDING":
            all_done = False
            break

    # 6. 如果全部完成，做提交检查并生成完整报告
    passed_factors = []
    checked_factors = []
    submitted_count = 0

    if all_done:
        print("[步骤5] 全部因子完成，运行提交检查...")
        passed_factors, checked_factors = run_submit_checks(
            client, factor_list=FACTOR_LIST
        )
        print()

        print("[步骤6] 正式提交通过检查的因子...")
        submitted_count = submit_passed_factors(client, passed_factors)
        print()
    else:
        print("[状态] 仍有因子未完成，本轮不做提交检查。")
        print("  下次运行将继续等待并提交剩余因子。")
        print()

    # 7. 生成报告
    print("[步骤7] 生成报告...")
    report_path = generate_report(client, passed_factors, checked_factors)
    print()

    # 汇总结果
    batch_completed = sum(
        1 for name, _, expr in FACTOR_LIST
        if (s := client.get_factor_status(expr, settings)) and s["status"] == "COMPLETED"
    )
    batch_pending = sum(
        1 for name, _, expr in FACTOR_LIST
        if (s := client.get_factor_status(expr, settings)) and s["status"] == "PENDING"
    )

    return {
        "report_path": report_path,
        "backtest_report_path": BACKTEST_REPORT_PATH,
        "total_factors": len(FACTOR_LIST),
        "completed": batch_completed,
        "pending": batch_pending,
        "failed": len(FACTOR_LIST) - batch_completed - batch_pending,
        "passed_submit_check": len(passed_factors),
        "officially_submitted": submitted_count,
        "all_done": all_done,
    }


# ============================================================
# 异步入口（CodeAct SDK 要求）
# ============================================================

async def main():
    from codeact_sdk import CodeActSDK

    # 参数解析
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    max_submit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    submit_interval = int(sys.argv[3]) if len(sys.argv) > 3 else 40
    wait_after = sys.argv[4].lower() == "true" if len(sys.argv) > 4 else True

    actual_mode = result_mode if result_mode != "auto" else "display_only"

    sdk = CodeActSDK()

    try:
        # 在线程池中运行同步代码（避免阻塞事件循环）
        import concurrent.futures
        loop = asyncio.get_running_loop()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = await loop.run_in_executor(
                pool, main_sync, result_mode, max_submit, submit_interval, wait_after
            )

        # 构建用户摘要
        if result["all_done"]:
            summary = (
                f"✅ 全部 28 个因子回测完成！\n"
                f"   - 完成: {result['completed']} 个\n"
                f"   - 失败: {result['failed']} 个\n"
                f"   - 通过提交检查: {result['passed_submit_check']} 个\n"
                f"   - 已正式提交: {result['officially_submitted']} 个"
            )
        else:
            summary = (
                f"⏳ 批次回测进行中...\n"
                f"   - 已完成: {result['completed']}/{result['total_factors']} 个\n"
                f"   - 进行中: {result['pending']} 个\n"
                f"   - 下次运行将继续处理剩余因子"
            )

        abs_report = os.path.abspath(result["report_path"])

        message = (
            f"{summary}\n\n"
            f"详细报告：[跃迁因子报告](computer://{abs_report})"
        )

        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=message,
            data={
                "report_path": result["report_path"],
                "backtest_report_path": result["backtest_report_path"],
                "completed": result["completed"],
                "pending": result["pending"],
                "failed": result["failed"],
                "passed_submit_check": result["passed_submit_check"],
                "officially_submitted": result["officially_submitted"],
                "all_done": result["all_done"],
            },
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"执行失败：{type(e).__name__}: {e}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
