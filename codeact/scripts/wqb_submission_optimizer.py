#!/usr/bin/env python3
"""
WQB 因子提交优化脚本 - wqb_submission_optimizer.py
=====================================================

目标：优化因子以通过 WQB 平台的提交检查（SUBMIT CHECK），核心是降低 SELF_CORRELATION
      自相关性，同时保持 Sharpe≥1.25 和 Fitness≥1.0。

功能：
  1. 诊断阶段：测试已有因子的提交检查结果，找规律
  2. 优化因子生成：降低vol权重、缩短vol周期、提高活跃度、混合高换手因子
  3. 批量回测：提交优化因子回测，SQLite去重
  4. 提交检查：对候选因子测试提交检查
  5. 报告生成：回测报告 + 提交结果报告

用法：
  python wqb_submission_optimizer.py [result_mode] [mode]

参数：
  result_mode: display_only / notify / auto (默认: display_only)
  mode:        diagnose / optimize / check / all (默认: all)
               - diagnose: 只运行诊断阶段（测试已有因子提交检查）
               - optimize: 只生成并回测优化因子
               - check:    只对候选因子做提交检查
               - all:      完整流程：诊断 → 优化回测 → 提交检查
"""

import asyncio
import sys
import os
import json
import time
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager

# 确保能导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from codeact_sdk import CodeActSDK
from wqb_api_client import WQBApiClient, WQBSimulation, DEFAULT_SETTINGS


# ============================================================
# 工具 Schema 版本常量
# ============================================================
TOOL_SCHEMA_VERSIONS = {
    "codeact_search_web": "v1_5ac1b0eba8c26f2a",
    "codeact_fetch_web": "v1_2c8d0580b3f93a58",
    "file_to_url": "v1_fe3416acf3d7b53b",
}

# ============================================================
# 常量配置
# ============================================================
BASE_URL = "https://api.worldquantbrain.com"
SUBMIT_INTERVAL = 40.0  # 回测提交间隔
SUBMIT_CHECK_INTERVAL = 12.0  # 提交检查间隔

DB_PATH = "./codeact/output/wqb_state.db"
REPORT_DIR = "./codeact/output"

# 提交检查阈值
CHECK_THRESHOLDS = {
    "LOW_SHARPE": 1.25,
    "LOW_FITNESS": 1.0,
    "HIGH_TURNOVER": 0.7,
    "LOW_TURNOVER": 0.01,
    "SELF_CORRELATION": 0.7,
}

# ============================================================
# 账号信息
# ============================================================
WQB_EMAIL = "q1z2q3@126.com"
WQB_PASSWORD = "W2025zq0118"

# ============================================================
# alpha_021 原始信号表达式
# ============================================================
ALPHA021_RAW_EXPR = (
    "subtract("
    "divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1)), "
    "divide(subtract(close, open), open)"
    ")"
)

# ============================================================
# 诊断用已有因子（alpha_id）
# ============================================================
DIAGNOSE_FACTORS = {
    "combo_d10_vol120_w8020": "O0xaOO91",   # Sharpe 2.24, Fitness 1.34, 已知SELF_CORR失败
    "alpha_021": "xAdqoYmb",                 # Sharpe 1.62, Fitness 0.94
    "reversal_5": "QPVxWaNK",                # Sharpe 1.09, 换手 30%
    "hist_vol_120": "zqmxAwmR",              # Sharpe 0.44, 换手 3%
    "alpha_005": "pwKmkoP3",                 # Sharpe 0.96, Fitness 1.23, 换手 8%
    "amihud_illiq": "akE68vZ6",              # Sharpe 1.08, 换手 2%
    "alpha_021_decay5": "vRvgKm8A",          # Sharpe 1.84, Fitness 0.86, 换手 74%
    "combo_raw_vol120_w7030_decay10": "akEvjnbW",  # Sharpe 1.99, Fitness 1.25
}


# ============================================================
# 提交检查数据库管理
# ============================================================
class SubmissionCheckDB:
    """提交检查结果数据库"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submit_checks (
                alpha_id TEXT PRIMARY KEY,
                factor_name TEXT,
                checked_at TEXT,
                status TEXT,
                self_correlation REAL,
                sharpe REAL,
                fitness REAL,
                turnover REAL,
                checks_json TEXT,
                passed INTEGER DEFAULT 0,
                error TEXT
            )
        """)
        try:
            conn.execute("ALTER TABLE submit_checks ADD COLUMN factor_name TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE submit_checks ADD COLUMN checks_json TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE submit_checks ADD COLUMN passed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE submit_checks ADD COLUMN error TEXT")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        conn.close()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_check_result(self, alpha_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM submit_checks WHERE alpha_id = ?", (alpha_id,)
            ).fetchone()
            if row:
                columns = [desc[0] for desc in conn.execute("SELECT * FROM submit_checks LIMIT 0").description]
                return dict(zip(columns, row))
        return None

    def save_check_result(self, alpha_id: str, factor_name: str, status: str,
                          self_correlation: float = None, sharpe: float = None,
                          fitness: float = None, turnover: float = None,
                          checks: dict = None, passed: int = 0, error: str = None):
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT alpha_id FROM submit_checks WHERE alpha_id = ?", (alpha_id,)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE submit_checks SET
                        factor_name = COALESCE(?, factor_name),
                        checked_at = ?,
                        status = ?,
                        self_correlation = COALESCE(?, self_correlation),
                        sharpe = COALESCE(?, sharpe),
                        fitness = COALESCE(?, fitness),
                        turnover = COALESCE(?, turnover),
                        checks_json = COALESCE(?, checks_json),
                        passed = COALESCE(?, passed),
                        error = COALESCE(?, error)
                    WHERE alpha_id = ?
                """, (factor_name, now, status, self_correlation, sharpe, fitness,
                      turnover, json.dumps(checks) if checks else None, passed,
                      error, alpha_id))
            else:
                conn.execute("""
                    INSERT INTO submit_checks (
                        alpha_id, factor_name, checked_at, status,
                        self_correlation, sharpe, fitness, turnover,
                        checks_json, passed, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (alpha_id, factor_name, now, status, self_correlation, sharpe,
                      fitness, turnover, json.dumps(checks) if checks else None,
                      passed, error))

    def list_all_checks(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM submit_checks ORDER BY passed DESC, self_correlation ASC"
            ).fetchall()
            columns = [desc[0] for desc in conn.execute("SELECT * FROM submit_checks LIMIT 0").description]
            return [dict(zip(columns, row)) for row in rows]


# ============================================================
# 提交检查功能
# ============================================================
def get_submit_check(client: WQBApiClient, alpha_id: str, factor_name: str = None,
                     verbose: bool = True) -> dict:
    """
    获取因子的提交检查结果
    
    通过 POST /alphas/{id}/submit 触发提交检查，然后 GET 查看结果。
    注意：这只是查看检查项状态，不会真的提交到生产。
    """
    import requests
    
    result = {
        "alpha_id": alpha_id,
        "factor_name": factor_name,
        "status": "UNKNOWN",
        "self_correlation": None,
        "sharpe": None,
        "fitness": None,
        "turnover": None,
        "checks": {},
        "passed": False,
        "error": None,
    }
    
    try:
        # 触发提交检查（POST submit）
        if verbose:
            print(f"  [提交检查] 触发 {alpha_id} ({factor_name or 'unknown'})...")
        
        submit_url = f"{BASE_URL}/alphas/{alpha_id}/submit"
        response = client._session.post(submit_url)
        
        # WQB API 行为：
        # - 201 Created: 提交成功（所有检查通过）
        # - 403 Forbidden: 检查未通过，但响应体包含检查结果
        # - 其他: 错误
        
        response_data = None
        try:
            response_data = response.json()
        except:
            response_data = {}
        
        if response.status_code in (200, 201, 403) and response_data:
            # 解析检查结果（无论是201通过还是403未通过，都有检查数据）
            result["status"] = "COMPLETED"
            
            # 检查结果可能在顶层，也可能在 "is" 字段下
            checks_source = response_data
            if "is" in response_data and isinstance(response_data["is"], dict):
                checks_source = response_data["is"]
            
            checks_list = checks_source.get("checks", [])
            checks_dict = {}
            
            for check in checks_list:
                check_name = check.get("name", "")
                # 结果字段可能叫 result 或 status
                check_result = check.get("result", check.get("status", ""))
                check_value = check.get("value")
                check_limit = check.get("limit")
                
                checks_dict[check_name] = {
                    "status": check_result,
                    "value": check_value,
                    "limit": check_limit,
                }
                
                # 提取关键指标
                if check_name == "SELF_CORRELATION":
                    result["self_correlation"] = check_value
                elif check_name == "LOW_SHARPE":
                    result["sharpe"] = check_value
                elif check_name == "LOW_FITNESS":
                    result["fitness"] = check_value
                elif check_name in ("HIGH_TURNOVER", "LOW_TURNOVER"):
                    if result["turnover"] is None:
                        result["turnover"] = check_value
            
            result["checks"] = checks_dict
            
            # 判断是否通过所有检查
            all_passed = all(
                c.get("status") in ("PASS", "PASSED", "OK")
                for c in checks_dict.values()
            ) and response.status_code == 201
            
            # 如果是 201，说明提交成功，所有检查都通过
            if response.status_code == 201:
                all_passed = True
            
            result["passed"] = all_passed
            
            if verbose:
                pass_count = sum(1 for c in checks_dict.values() if c.get("status") in ("PASS", "PASSED", "OK"))
                total_count = len(checks_dict)
                sc = result.get("self_correlation")
                sc_str = f"{sc:.4f}" if sc else "N/A"
                sh = result.get("sharpe")
                sh_str = f"{sh:.2f}" if sh else "N/A"
                ft = result.get("fitness")
                ft_str = f"{ft:.2f}" if ft else "N/A"
                status_str = "✓ 通过" if all_passed else "✗ 未通过"
                print(f"    {status_str}: {pass_count}/{total_count} 检查项, "
                      f"SELF_CORR={sc_str}, "
                      f"Sharpe={sh_str}, Fitness={ft_str}")
        
        elif response.status_code == 400:
            # 可能已经是提交状态，直接获取alpha信息
            if verbose:
                print(f"    返回400，尝试直接获取alpha信息...")
            alpha_data = client.get_alpha(alpha_id)
            result["status"] = "INFO_ONLY"
            is_data = alpha_data.get("is", {})
            result["sharpe"] = is_data.get("sharpe")
            result["fitness"] = is_data.get("fitness")
            result["turnover"] = is_data.get("turnover")
            result["error"] = f"HTTP 400: {response.text[:200]}"
            
        else:
            result["status"] = "ERROR"
            result["error"] = f"HTTP {response.status_code}: {response.text[:200]}"
            if verbose:
                print(f"    错误: {result['error']}")
                
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)
        if verbose:
            print(f"    异常: {e}")
    
    return result


async def batch_submit_check(client: WQBApiClient, factors: List[Tuple[str, str]],
                              check_db: SubmissionCheckDB,
                              interval: float = SUBMIT_CHECK_INTERVAL,
                              force: bool = False) -> List[dict]:
    """
    批量进行提交检查
    
    Args:
        factors: [(factor_name, alpha_id), ...]
        check_db: 提交检查数据库
        interval: 检查间隔（秒）
        force: 是否强制重新检查
    
    Returns:
        检查结果列表
    """
    results = []
    
    for i, (factor_name, alpha_id) in enumerate(factors):
        # 检查缓存
        if not force:
            cached = check_db.get_check_result(alpha_id)
            if cached and cached.get("status") in ("COMPLETED", "INFO_ONLY"):
                print(f"  [{i+1}/{len(factors)}] 缓存命中: {factor_name} ({alpha_id})")
                results.append(cached)
                continue
        
        print(f"  [{i+1}/{len(factors)}] 检查: {factor_name} ({alpha_id})")
        
        # 执行提交检查
        loop = asyncio.get_event_loop()
        check_result = await loop.run_in_executor(
            None, get_submit_check, client, alpha_id, factor_name
        )
        
        # 保存结果
        check_db.save_check_result(
            alpha_id=alpha_id,
            factor_name=factor_name,
            status=check_result["status"],
            self_correlation=check_result.get("self_correlation"),
            sharpe=check_result.get("sharpe"),
            fitness=check_result.get("fitness"),
            turnover=check_result.get("turnover"),
            checks=check_result.get("checks"),
            passed=1 if check_result.get("passed") else 0,
            error=check_result.get("error"),
        )
        
        results.append(check_result)
        
        # 间隔
        if i < len(factors) - 1:
            await asyncio.sleep(interval)
    
    return results


# ============================================================
# 优化因子生成
# ============================================================
def generate_optimization_factors() -> List[Tuple[str, str, dict]]:
    """
    生成优化因子列表
    
    Returns:
        [(factor_name, expression, settings), ...]
    """
    factors = []
    
    # 基础设置
    base_settings = dict(DEFAULT_SETTINGS)
    base_settings.update({
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "decay": 15,
        "neutralization": "SUBINDUSTRY",
        "truncation": 0.08,
        "testPeriod": "P1Y6M",
    })
    
    # ---- 优化方向1：降低 vol 因子权重 + 缩短 vol 周期 ----
    
    # vol20 替代 vol120
    vol20_expr = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 20)"
    vol60_expr = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 60)"
    vol120_expr = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 120)"
    
    # 1. combo_d10_vol20_w9010: 90% alpha_021 + 10% vol20 (reverse)
    name = "combo_d10_vol20_w9010"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.9), multiply(reverse({vol20_expr}), 0.1)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 2. combo_d10_vol20_w8020: 80% alpha_021 + 20% vol20
    name = "combo_d10_vol20_w8020"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.8), multiply(reverse({vol20_expr}), 0.2)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 3. combo_d10_vol60_w8515: 85% alpha_021 + 15% vol60
    name = "combo_d10_vol60_w8515"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.85), multiply(reverse({vol60_expr}), 0.15)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 4. combo_d10_vol60_w7525: 75% alpha_021 + 25% vol60
    name = "combo_d10_vol60_w7525"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.75), multiply(reverse({vol60_expr}), 0.25)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 5. combo_d10_vol120_w9010: 90% alpha_021 + 10% vol120 (降低权重)
    name = "combo_d10_vol120_w9010"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.9), multiply(reverse({vol120_expr}), 0.1)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 6. combo_d10_vol120_w9505: 95% alpha_021 + 5% vol120 (极低权重)
    name = "combo_d10_vol120_w9505"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.95), multiply(reverse({vol120_expr}), 0.05)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 7. combo_d10_deltavol20_w8020: 80% alpha_021 + 20% reverse(ts_delta(vol20, 5))
    delta_vol20_expr = f"ts_delta({vol20_expr}, 5)"
    name = "combo_d10_deltavol20_w8020"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.8), multiply(reverse({delta_vol20_expr}), 0.2)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 8. combo_d10_deltavol60_w8515: 85% alpha_021 + 15% reverse(ts_delta(vol60, 5))
    delta_vol60_expr = f"ts_delta({vol60_expr}, 5)"
    name = "combo_d10_deltavol60_w8515"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.85), multiply(reverse({delta_vol60_expr}), 0.15)))"
    factors.append((name, expr, dict(base_settings)))
    
    # ---- 优化方向2：提高 alpha_021 本身的活跃度 ----
    
    # 9. alpha_021_tsdelta1: ts_delta(alpha_021, 1) 因子的变化量
    name = "alpha_021_tsdelta1"
    expr = f"rank(ts_delta({ALPHA021_RAW_EXPR}, 1))"
    factors.append((name, expr, dict(base_settings)))
    
    # 10. alpha_021_v5d: 隔夜收益5日均值 - 日内收益5日均值
    overnight_expr = "divide(subtract(open, ts_delay(close, 1)), ts_delay(close, 1))"
    intraday_expr = "divide(subtract(close, open), open)"
    v5d_expr = f"subtract(ts_mean({overnight_expr}, 5), ts_mean({intraday_expr}, 5))"
    name = "alpha_021_v5d"
    expr = f"rank({v5d_expr})"
    factors.append((name, expr, dict(base_settings)))
    
    # 11. alpha_021_decay5_v2: decay=5 (高换手版本，确认数据库中是否已有)
    decay5_settings = dict(base_settings)
    decay5_settings["decay"] = 5
    name = "alpha_021_decay5_v2"
    expr = f"rank({ALPHA021_RAW_EXPR})"
    factors.append((name, expr, decay5_settings))
    
    # 12. alpha_021_v5d_decay5: v5d版本 + decay5
    name = "alpha_021_v5d_decay5"
    expr = f"rank({v5d_expr})"
    factors.append((name, expr, decay5_settings))
    
    # ---- 优化方向3：加入高换手因子降低自相关 ----
    
    # 13. combo_d10_rev5_w9010: 90% alpha_021 + 10% reversal_5
    rev5_expr = "ts_delta(close, 5)"
    name = "combo_d10_rev5_w9010"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.9), multiply(reverse({rev5_expr}), 0.1)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 14. combo_d10_rev5_w8020: 80% alpha_021 + 20% reversal_5
    name = "combo_d10_rev5_w8020"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.8), multiply(reverse({rev5_expr}), 0.2)))"
    factors.append((name, expr, dict(base_settings)))
    
    # 15. combo_d10_vol20_rev5_w702010: 70% a021 + 20% vol20 + 10% rev5
    name = "combo_d10_vol20_rev5_w702010"
    expr = f"rank(add(add(multiply({ALPHA021_RAW_EXPR}, 0.7), multiply(reverse({vol20_expr}), 0.2)), multiply(reverse({rev5_expr}), 0.1)))"
    factors.append((name, expr, dict(base_settings)))
    
    # ---- 优化方向4：提高 Fitness 的尝试 ----
    
    # 16. alpha_021_neut_none_v2: 无neutralization (已知Fitness高但Sharpe低)
    neut_none_settings = dict(base_settings)
    neut_none_settings["neutralization"] = "NONE"
    name = "alpha_021_neut_none_v2"
    expr = f"rank({ALPHA021_RAW_EXPR})"
    factors.append((name, expr, neut_none_settings))
    
    # 17. combo_d10_vol120_w8020_neut_none: 组合因子 + 无neutralization
    name = "combo_d10_vol120_w8020_neut_none"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.8), multiply(reverse({vol120_expr}), 0.2)))"
    factors.append((name, expr, neut_none_settings))
    
    # 18. alpha_021_trunc15: 更高的truncation
    trunc15_settings = dict(base_settings)
    trunc15_settings["truncation"] = 0.15
    name = "alpha_021_trunc15"
    expr = f"rank({ALPHA021_RAW_EXPR})"
    factors.append((name, expr, trunc15_settings))
    
    # 19. combo_d10_vol20_w8515_decay5: decay5 + vol20组合
    decay5_vol20_settings = dict(base_settings)
    decay5_vol20_settings["decay"] = 5
    name = "combo_d10_vol20_w8515_decay5"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.85), multiply(reverse({vol20_expr}), 0.15)))"
    factors.append((name, expr, decay5_vol20_settings))
    
    # 20. combo_d5_vol20_w8020: decay=5 + vol20组合
    decay5_settings_d5 = dict(base_settings)
    decay5_settings_d5["decay"] = 5
    name = "combo_d5_vol20_w8020"
    expr = f"rank(add(multiply({ALPHA021_RAW_EXPR}, 0.8), multiply(reverse({vol20_expr}), 0.2)))"
    factors.append((name, expr, decay5_settings_d5))
    
    print(f"[优化因子] 生成 {len(factors)} 个候选因子")
    for name, _, settings in factors:
        print(f"  - {name} (decay={settings.get('decay')}, neut={settings.get('neutralization')})")
    
    return factors


# ============================================================
# 批量回测
# ============================================================
async def batch_backtest(client: WQBApiClient, factors: List[Tuple[str, str, dict]],
                         submit_interval: float = SUBMIT_INTERVAL) -> List[dict]:
    """
    批量提交回测并等待结果
    
    Returns:
        结果列表
    """
    results = []
    
    for i, (factor_name, expression, settings) in enumerate(factors):
        # 检查缓存
        cached = client.get_cached_alpha(expression, settings)
        if cached and cached.get("status") == "COMPLETED":
            print(f"  [{i+1}/{len(factors)}] 缓存命中: {factor_name} "
                  f"(Sharpe={cached.get('sharpe')}, Fitness={cached.get('fitness')})")
            results.append({
                "factor_name": factor_name,
                "expression": expression,
                "settings": settings,
                "alpha_id": cached.get("alpha_id"),
                "sharpe": cached.get("sharpe"),
                "fitness": cached.get("fitness"),
                "turnover": cached.get("turnover"),
                "status": "COMPLETED",
                "from_cache": True,
            })
            continue
        
        print(f"  [{i+1}/{len(factors)}] 提交: {factor_name}...")
        
        try:
            loop = asyncio.get_event_loop()
            sim = await loop.run_in_executor(
                None, client.simulate, expression, settings
            )
            
            # 保存提交记录
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category="optimization",
                progress_url=sim.progress_url,
                status="PENDING",
            )
            
            results.append({
                "factor_name": factor_name,
                "expression": expression,
                "settings": settings,
                "sim": sim,
                "status": "PENDING",
                "from_cache": False,
            })
            
        except Exception as e:
            print(f"    提交失败: {e}")
            client.save_alpha_result(
                expression=expression,
                settings=settings,
                factor_name=factor_name,
                category="optimization",
                status="FAILED",
                error=str(e),
            )
            results.append({
                "factor_name": factor_name,
                "expression": expression,
                "settings": settings,
                "status": "FAILED",
                "error": str(e),
                "from_cache": False,
            })
        
        # 提交间隔
        if i < len(factors) - 1:
            await asyncio.sleep(submit_interval)
    
    # 等待所有进行中的回测完成
    pending = [r for r in results if r.get("status") == "PENDING" and r.get("sim")]
    if pending:
        print(f"\n[等待] {len(pending)} 个回测进行中...")
        
        all_completed = False
        start_time = asyncio.get_event_loop().time()
        max_wait = 600  # 最多等10分钟
        
        while not all_completed and (asyncio.get_event_loop().time() - start_time) < max_wait:
            all_completed = True
            
            for r in pending:
                if r["status"] != "PENDING":
                    continue
                
                sim = r["sim"]
                try:
                    loop = asyncio.get_event_loop()
                    done = await loop.run_in_executor(
                        None, sim.wait, False, 5.0
                    )
                    
                    if done:
                        r["status"] = "COMPLETED"
                        r["alpha_id"] = sim.alpha_id
                        
                        # 获取指标
                        metrics = sim.get_metrics()
                        r["sharpe"] = metrics.get("sharpe")
                        r["fitness"] = metrics.get("fitness")
                        r["turnover"] = metrics.get("turnover")
                        r["is_summary"] = metrics.get("is_summary")
                        
                        # 保存结果
                        client.save_alpha_result(
                            expression=r["expression"],
                            settings=r["settings"],
                            factor_name=r["factor_name"],
                            category="optimization",
                            alpha_id=sim.alpha_id,
                            status="COMPLETED",
                            metrics=metrics,
                            is_summary=metrics.get("is_summary"),
                        )
                        
                        print(f"  ✓ {r['factor_name']}: Sharpe={r['sharpe']}, "
                              f"Fitness={r['fitness']}, Turnover={r['turnover']}")
                    else:
                        all_completed = False
                        
                except Exception as e:
                    r["status"] = "FAILED"
                    r["error"] = str(e)
                    print(f"  ✗ {r['factor_name']}: {e}")
            
            if not all_completed:
                await asyncio.sleep(5)
        
        # 检查超时的
        timeout_count = sum(1 for r in pending if r.get("status") == "PENDING")
        if timeout_count > 0:
            print(f"\n[超时] {timeout_count} 个回测仍在进行中，将在后台继续")
    
    return results


# ============================================================
# 报告生成
# ============================================================
def generate_backtest_report(results: List[dict], diagnose_results: List[dict] = None) -> str:
    """生成回测报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = []
    lines.append("# WQB 因子优化回测报告")
    lines.append("")
    lines.append(f"生成时间: {now}")
    lines.append("")
    
    # 诊断结果
    if diagnose_results:
        lines.append("## 诊断阶段：已有因子提交检查")
        lines.append("")
        lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手 | 自相关性 | 通过 |")
        lines.append("|---------|----------|--------|---------|------|---------|------|")
        
        for r in sorted(diagnose_results, key=lambda x: x.get("self_correlation") or 999):
            sc = r.get("self_correlation")
            sc_str = f"{sc:.4f}" if sc else "N/A"
            passed = "✓" if r.get("passed") else "✗"
            sharpe = r.get("sharpe")
            fit = r.get("fitness")
            to = r.get("turnover")
            
            sharpe_str = f"{sharpe:.2f}" if sharpe else "N/A"
            fit_str = f"{fit:.2f}" if fit else "N/A"
            to_str = f"{to:.4f}" if to else "N/A"
            lines.append(
                f"| {r.get('factor_name', 'N/A')} "
                f"| {r.get('alpha_id', 'N/A')} "
                f"| {sharpe_str} "
                f"| {fit_str} "
                f"| {to_str} "
                f"| {sc_str} "
                f"| {passed} |"
            )
        
        lines.append("")
        
        # 分析
        lines.append("### 诊断分析")
        lines.append("")
        high_sc = [r for r in diagnose_results if r.get("self_correlation") and r["self_correlation"] > 0.7]
        low_sc = [r for r in diagnose_results if r.get("self_correlation") and r["self_correlation"] <= 0.7]
        
        lines.append(f"- 自相关性 > 0.7 的因子: {len(high_sc)} 个")
        for r in high_sc:
            lines.append(f"  - {r.get('factor_name')}: {r.get('self_correlation'):.4f}")
        
        lines.append(f"- 自相关性 ≤ 0.7 的因子: {len(low_sc)} 个")
        for r in low_sc:
            lines.append(f"  - {r.get('factor_name')}: {r.get('self_correlation'):.4f}")
        
        lines.append("")
    
    # 优化因子回测结果
    completed = [r for r in results if r.get("status") == "COMPLETED"]
    failed = [r for r in results if r.get("status") == "FAILED"]
    pending = [r for r in results if r.get("status") == "PENDING"]
    
    lines.append("## 优化因子回测结果")
    lines.append("")
    lines.append(f"- 总因子数: {len(results)}")
    lines.append(f"- 已完成: {len(completed)}")
    lines.append(f"- 失败: {len(failed)}")
    lines.append(f"- 进行中: {len(pending)}")
    lines.append("")
    
    if completed:
        lines.append("### 已完成因子排名（按Sharpe降序）")
        lines.append("")
        lines.append("| 排名 | 因子名称 | Sharpe | Fitness | 换手 | 候选资格 |")
        lines.append("|-----|---------|--------|---------|------|---------|")
        
        for i, r in enumerate(sorted(completed, key=lambda x: x.get("sharpe") or 0, reverse=True), 1):
            sharpe = r.get("sharpe") or 0
            fitness = r.get("fitness") or 0
            turnover = r.get("turnover") or 0
            
            # 候选资格：Sharpe≥1.25 且 Fitness≥1.0
            is_candidate = sharpe >= 1.25 and fitness >= 1.0
            candidate_str = "✓ 候选" if is_candidate else "✗"
            
            lines.append(
                f"| {i} "
                f"| {r['factor_name']} "
                f"| {sharpe:.2f} "
                f"| {fitness:.2f} "
                f"| {turnover:.4f} "
                f"| {candidate_str} |"
            )
        
        lines.append("")
        
        # 候选因子
        candidates = [r for r in completed if (r.get("sharpe") or 0) >= 1.25 and (r.get("fitness") or 0) >= 1.0]
        if candidates:
            lines.append(f"### 候选因子（Sharpe≥1.25 且 Fitness≥1.0）: {len(candidates)} 个")
            lines.append("")
            for r in sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True):
                lines.append(f"- **{r['factor_name']}**: Sharpe={r['sharpe']:.2f}, "
                             f"Fitness={r['fitness']:.2f}, Turnover={r['turnover']:.4f}, "
                             f"Alpha ID: {r.get('alpha_id', 'N/A')}")
            lines.append("")
    
    if failed:
        lines.append("### 失败因子")
        lines.append("")
        for r in failed:
            lines.append(f"- {r['factor_name']}: {r.get('error', 'Unknown error')}")
        lines.append("")
    
    if pending:
        lines.append("### 进行中因子")
        lines.append("")
        for r in pending:
            lines.append(f"- {r['factor_name']}")
        lines.append("")
    
    return "\n".join(lines)


def generate_submission_report(check_results: List[dict]) -> str:
    """生成提交检查报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = []
    lines.append("# WQB 因子提交检查报告")
    lines.append("")
    lines.append(f"生成时间: {now}")
    lines.append("")
    
    passed = [r for r in check_results if r.get("passed")]
    failed = [r for r in check_results if not r.get("passed") and r.get("status") in ("COMPLETED", "INFO_ONLY")]
    
    lines.append(f"## 总体结果")
    lines.append("")
    lines.append(f"- 检查因子总数: {len(check_results)}")
    lines.append(f"- 通过所有检查: {len(passed)} 个")
    lines.append(f"- 未通过: {len(failed)} 个")
    lines.append("")
    
    if passed:
        lines.append("## ✅ 通过所有提交检查的因子")
        lines.append("")
        lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手 | 自相关性 |")
        lines.append("|---------|----------|--------|---------|------|---------|")
        
        for r in sorted(passed, key=lambda x: x.get("sharpe") or 0, reverse=True):
            lines.append(
                f"| {r.get('factor_name', 'N/A')} "
                f"| {r.get('alpha_id', 'N/A')} "
                f"| {r.get('sharpe', 'N/A')} "
                f"| {r.get('fitness', 'N/A')} "
                f"| {r.get('turnover', 'N/A')} "
                f"| {r.get('self_correlation', 'N/A')} |"
            )
        lines.append("")
    
    if failed:
        lines.append("## ❌ 未通过提交检查的因子")
        lines.append("")
        lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手 | 自相关性 | 失败项 |")
        lines.append("|---------|----------|--------|---------|------|---------|--------|")
        
        for r in sorted(failed, key=lambda x: x.get("self_correlation") or 999):
            # 找出失败的检查项
            checks = r.get("checks") or {}
            if isinstance(checks, str):
                try:
                    checks = json.loads(checks)
                except:
                    checks = {}
            
            failed_items = []
            for name, check in checks.items():
                if isinstance(check, dict):
                    status = check.get("status", "")
                    if status not in ("PASS", "PASSED", "OK"):
                        val = check.get("value", "N/A")
                        failed_items.append(f"{name}({val})")
            
            failed_str = ", ".join(failed_items) if failed_items else "未知"
            
            sc = r.get("self_correlation")
            sc_str = f"{sc:.4f}" if sc else "N/A"
            
            lines.append(
                f"| {r.get('factor_name', 'N/A')} "
                f"| {r.get('alpha_id', 'N/A')} "
                f"| {r.get('sharpe', 'N/A')} "
                f"| {r.get('fitness', 'N/A')} "
                f"| {r.get('turnover', 'N/A')} "
                f"| {sc_str} "
                f"| {failed_str} |"
            )
        lines.append("")
    
    # 详细检查结果
    lines.append("## 详细检查结果")
    lines.append("")
    
    for r in check_results:
        lines.append(f"### {r.get('factor_name', 'N/A')} ({r.get('alpha_id', 'N/A')})")
        lines.append("")
        lines.append(f"- 状态: {r.get('status', 'N/A')}")
        lines.append(f"- Sharpe: {r.get('sharpe', 'N/A')}")
        lines.append(f"- Fitness: {r.get('fitness', 'N/A')}")
        lines.append(f"- 换手率: {r.get('turnover', 'N/A')}")
        lines.append(f"- 自相关性: {r.get('self_correlation', 'N/A')}")
        
        checks = r.get("checks") or {}
        if isinstance(checks, str):
            try:
                checks = json.loads(checks)
            except:
                checks = {}
        
        if checks:
            lines.append("- 检查项:")
            for name, check in checks.items():
                if isinstance(check, dict):
                    status = check.get("status", "N/A")
                    value = check.get("value", "N/A")
                    status_icon = "✅" if status in ("PASS", "PASSED", "OK") else "❌"
                    lines.append(f"  - {status_icon} {name}: {status} (value={value})")
        
        if r.get("error"):
            lines.append(f"- 错误: {r['error']}")
        
        lines.append("")
    
    return "\n".join(lines)


# ============================================================
# 主函数
# ============================================================
async def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    max_factors = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    
    print(f"[参数] result_mode={result_mode}, mode={mode}, max_factors={max_factors}")
    print(f"[配置] 回测提交间隔: {SUBMIT_INTERVAL}s, 提交检查间隔: {SUBMIT_CHECK_INTERVAL}s")
    
    sdk = CodeActSDK()
    actual_mode = result_mode if result_mode != "auto" else "display_only"
    
    try:
        # 初始化
        print("\n[初始化] 登录 WQB 平台...")
        client = WQBApiClient.login(WQB_EMAIL, WQB_PASSWORD)
        check_db = SubmissionCheckDB(DB_PATH)
        print("  ✓ 登录成功")
        
        diagnose_results = []
        backtest_results = []
        check_results = []
        
        # ========== 阶段1：诊断 ==========
        if mode in ("diagnose", "all"):
            print("\n" + "=" * 60)
            print("【阶段1：诊断】测试已有因子的提交检查结果")
            print("=" * 60)
            
            factors_to_check = list(DIAGNOSE_FACTORS.items())
            diagnose_results = await batch_submit_check(
                client, factors_to_check, check_db,
                interval=SUBMIT_CHECK_INTERVAL,
                force=False,
            )
            
            print(f"\n[诊断完成] 共检查 {len(diagnose_results)} 个因子")
            passed_count = sum(1 for r in diagnose_results if r.get("passed"))
            print(f"  通过: {passed_count} 个")
            print(f"  未通过: {len(diagnose_results) - passed_count} 个")
        
        # ========== 阶段2：优化因子回测 ==========
        if mode in ("optimize", "all"):
            print("\n" + "=" * 60)
            print("【阶段2：优化】生成并回测优化因子")
            print("=" * 60)
            
            # 生成优化因子
            opt_factors = generate_optimization_factors()
            
            # 限制数量（优先保留前面的，因为生成时已经按优先级排序）
            if len(opt_factors) > max_factors:
                opt_factors = opt_factors[:max_factors]
                print(f"\n[优化因子] 限制为前 {max_factors} 个")
            
            # 批量回测
            print(f"\n[批量回测] 提交 {len(opt_factors)} 个因子...")
            backtest_results = await batch_backtest(
                client, opt_factors,
                submit_interval=SUBMIT_INTERVAL,
            )
            
            completed = [r for r in backtest_results if r.get("status") == "COMPLETED"]
            print(f"\n[回测完成] 已完成 {len(completed)}/{len(backtest_results)} 个")
            
            # 找出候选因子
            candidates = [r for r in completed
                         if (r.get("sharpe") or 0) >= 1.25
                         and (r.get("fitness") or 0) >= 1.0]
            print(f"[候选因子] Sharpe≥1.25 且 Fitness≥1.0: {len(candidates)} 个")
            for c in sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True):
                print(f"  - {c['factor_name']}: Sharpe={c['sharpe']:.2f}, "
                      f"Fitness={c['fitness']:.2f}, AlphaID={c.get('alpha_id', 'N/A')}")
        
        # ========== 阶段3：提交检查 ==========
        if mode in ("check", "all"):
            print("\n" + "=" * 60)
            print("【阶段3：提交检查】对候选因子进行提交检查")
            print("=" * 60)
            
            # 获取所有满足 Sharpe≥1.25 且 Fitness≥1.0 的因子
            all_results = client.list_all_results(status="COMPLETED")
            candidates = [r for r in all_results
                         if (r.get("sharpe") or 0) >= 1.25
                         and (r.get("fitness") or 0) >= 1.0
                         and r.get("alpha_id")]
            
            # 按 Sharpe 排序
            candidates.sort(key=lambda x: x.get("sharpe") or 0, reverse=True)
            
            # 优先选择可能低自相关的因子（高换手的）
            # 先按换手降序，再按Sharpe降序
            candidates.sort(key=lambda x: (x.get("turnover") or 0, x.get("sharpe") or 0), reverse=True)
            
            print(f"\n[候选因子] 共 {len(candidates)} 个满足 Sharpe≥1.25 且 Fitness≥1.0")
            
            # 最多检查前20个
            to_check = candidates[:20]
            factors_to_check = [(r.get("factor_name", f"factor_{i}"), r["alpha_id"])
                               for i, r in enumerate(to_check) if r.get("alpha_id")]
            
            print(f"[提交检查] 检查 {len(factors_to_check)} 个候选因子...")
            
            check_results = await batch_submit_check(
                client, factors_to_check, check_db,
                interval=SUBMIT_CHECK_INTERVAL,
                force=False,
            )
            
            passed = [r for r in check_results if r.get("passed")]
            print(f"\n[检查完成] 通过: {len(passed)}/{len(check_results)}")
            
            if passed:
                print("\n🎉 通过所有提交检查的因子:")
                for r in passed:
                    print(f"  ✓ {r.get('factor_name')} ({r.get('alpha_id')}): "
                          f"Sharpe={r.get('sharpe')}, Fitness={r.get('fitness')}, "
                          f"SelfCorr={r.get('self_correlation')}")
        
        # ========== 生成报告 ==========
        print("\n" + "=" * 60)
        print("【报告生成】")
        print("=" * 60)
        
        # 合并所有检查结果
        all_checks = check_db.list_all_checks()
        
        # 回测报告
        if backtest_results or diagnose_results:
            backtest_report = generate_backtest_report(backtest_results, diagnose_results)
            backtest_report_path = os.path.join(REPORT_DIR, "wqb_backtest_report.md")
            os.makedirs(REPORT_DIR, exist_ok=True)
            with open(backtest_report_path, "w", encoding="utf-8") as f:
                f.write(backtest_report)
            print(f"  ✓ 回测报告: {backtest_report_path}")
        
        # 提交检查报告
        submission_report = generate_submission_report(all_checks)
        submission_report_path = os.path.join(REPORT_DIR, "wqb_submission_report.md")
        with open(submission_report_path, "w", encoding="utf-8") as f:
            f.write(submission_report)
        print(f"  ✓ 提交报告: {submission_report_path}")
        
        # ========== 提交结果 ==========
        passed_factors = [r for r in all_checks if r.get("passed")]
        
        # 构造摘要消息
        msg_parts = []
        msg_parts.append("WQB 因子提交优化完成")
        msg_parts.append("")
        
        if passed_factors:
            msg_parts.append(f"🎉 找到 {len(passed_factors)} 个通过所有提交检查的因子!")
            for r in passed_factors[:5]:
                msg_parts.append(f"  - {r.get('factor_name')}: Sharpe={r.get('sharpe')}, "
                                 f"Fitness={r.get('fitness')}, SelfCorr={r.get('self_correlation')}")
        else:
            msg_parts.append("⚠️ 尚未找到通过所有提交检查的因子")
            # 找出自相关性最低的候选
            candidates_with_sc = [r for r in all_checks if r.get("self_correlation") is not None
                                 and r.get("sharpe") and r.get("fitness")
                                 and float(r.get("sharpe", 0)) >= 1.25
                                 and float(r.get("fitness", 0)) >= 1.0]
            if candidates_with_sc:
                best = min(candidates_with_sc, key=lambda x: x.get("self_correlation") or 999)
                msg_parts.append(f"  最低自相关候选: {best.get('factor_name')}, "
                                 f"SelfCorr={best.get('self_correlation'):.4f}")
        
        msg_parts.append("")
        msg_parts.append(f"详细报告:")
        abs_bt = os.path.abspath(os.path.join(REPORT_DIR, "wqb_backtest_report.md"))
        abs_sr = os.path.abspath(submission_report_path)
        msg_parts.append(f"- [回测报告](computer://{abs_bt})")
        msg_parts.append(f"- [提交检查报告](computer://{abs_sr})")
        
        message = "\n".join(msg_parts)
        
        await sdk.submit_result(
            result_mode=actual_mode,
            status="success",
            message=message,
            data={
                "passed_count": len(passed_factors),
                "total_checked": len(all_checks),
                "backtest_report_path": os.path.join(REPORT_DIR, "wqb_backtest_report.md"),
                "submission_report_path": submission_report_path,
                "passed_factors": [
                    {"name": r.get("factor_name"), "alpha_id": r.get("alpha_id"),
                     "sharpe": r.get("sharpe"), "fitness": r.get("fitness"),
                     "self_correlation": r.get("self_correlation")}
                    for r in passed_factors
                ],
            },
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"因子优化执行失败: {type(e).__name__}: {e}",
            data={"error_type": type(e).__name__},
        )


if __name__ == "__main__":
    asyncio.run(main())
