#!/usr/bin/env python3
"""
WQB d5自相关低谷突破 - 批量回测+提交检查+正式发布 (v2)
============================================================

基于d5自相关低谷（SC=0.5838），精调vol20权重找到SC≤0.7且Fitness≥1.0的甜蜜点。

核心发现（v1验证结果）：
- decay=15时，vol20信号被15日衰减平滑，SC≈0.98，vol20几乎无效果
- decay=0时，d5自身SC≈0.71，加入vol20后SC仍在0.71-0.72
- 无论vol20权重多少（0.5%~2%），SC基本固定在0.71-0.72
- 唯一SC<0.7的是combo_d5_volume_confirm (SC=0.6553)但Fitness仅0.52

策略调整：
- 阶段1：使用decay=0测试vol20权重，接受SC≈0.71的事实
- 阶段2：测试乘法协同信号（volume_confirm, vol5等）
- 阶段3：对Sharpe≥1.25且Fitness≥1.0的因子执行8项提交检查
- 阶段4：对通过检查的因子正式提交

用法：
  python wqb_d5_breakthrough_submit.py [result_mode] [email] [password] [db_path] [report_path]

状态表：
  - alphas: 存储因子回测结果，expr_hash为主键去重
  - self_corr: 存储自相关检查结果
  - check_results: 存储8项提交检查结果
  - submit_checks: 存储提交检查汇总状态
"""

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ============================================================
# 路径配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ACE_LIB_DIR = os.path.join(SCRIPT_DIR, "ace_lib")
sys.path.insert(0, ACE_LIB_DIR)
sys.path.insert(0, SCRIPT_DIR)

from ace_lib import (
    start_session,
    generate_alpha,
    simulate_alpha_list,
    get_self_corr,
    get_check_submission,
)

# ============================================================
# 常量
# ============================================================

SUBMIT_INTERVAL = 45.0

SUBMISSION_THRESHOLDS = {
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
# 默认设置（decay=15为基准，但vol20组合用decay=0）
# ============================================================

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 15,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "maxTrade": "ON",
    "language": "FASTEXPR",
    "visualization": False,
}

# ============================================================
# 表达式定义
# ============================================================

D5_EXPR = "ts_decay_linear(subtract(divide(open, ts_delay(close, 1)), divide(close, open)), 5)"
VOL20_EXPR = "multiply(ts_std_dev(log(divide(close, ts_delay(close, 1))), 20), sqrt(252))"
VOL5_EXPR = "ts_std_dev(log(divide(close, ts_delay(close, 1))), 5)"


def make_combo_expr(d5_weight: float, vol20_weight: float) -> str:
    """生成 d5 + vol20 组合表达式"""
    return f"add(multiply({d5_weight}, {D5_EXPR}), multiply({vol20_weight}, multiply(-1, ts_rank({VOL20_EXPR}, 20))))"


# ============================================================
# 阶段1：vol20权重精调（使用decay=0，之前的成功测试已验证此设置有效）
# ============================================================

PHASE1_FACTORS = [
    {
        "name": "combo_d5_vol20_w98515",
        "expr": make_combo_expr(0.985, 0.015),
        "desc": "98.5% d5 + 1.5% (-ts_rank(vol20,20)), decay=0",
        "settings_override": {"decay": 0},
    },
    {
        "name": "combo_d5_vol20_w99010",
        "expr": make_combo_expr(0.99, 0.01),
        "desc": "99% d5 + 1% (-ts_rank(vol20,20)), decay=0",
        "settings_override": {"decay": 0},
    },
    {
        "name": "combo_d5_vol20_w99505",
        "expr": make_combo_expr(0.995, 0.005),
        "desc": "99.5% d5 + 0.5% (-ts_rank(vol20,20)), decay=0",
        "settings_override": {"decay": 0},
    },
    {
        "name": "combo_d5_vol20_w98218",
        "expr": make_combo_expr(0.982, 0.018),
        "desc": "98.2% d5 + 1.8% (-ts_rank(vol20,20)), decay=0",
        "settings_override": {"decay": 0},
    },
]

# ============================================================
# 阶段2：d5协同信号
# ============================================================

PHASE2_FACTORS = [
    {
        "name": "combo_d5_volume_confirm",
        "expr": f"multiply({D5_EXPR}, ts_rank(volume, 5))",
        "desc": "d5 * ts_rank(volume, 5), decay=0",
        "settings_override": {"decay": 0},
    },
    {
        "name": "combo_d5_vol5",
        "expr": f"multiply({D5_EXPR}, multiply(-1, ts_rank({VOL5_EXPR}, 5)))",
        "desc": "d5 * (-ts_rank(volatility_5, 5)), decay=0",
        "settings_override": {"decay": 0},
    },
    {
        "name": "alpha_021_d5_neut_none",
        "expr": D5_EXPR,
        "desc": "d5原始表达式 + neutralization=NONE, decay=0",
        "settings_override": {"decay": 0, "neutralization": "NONE"},
    },
]

# ============================================================
# 工具函数
# ============================================================

def normalize_settings(settings: Dict) -> Dict:
    full = dict(DEFAULT_SETTINGS)
    full.update(settings)
    return full


def expr_hash(expr: str, settings: Dict) -> str:
    norm = normalize_settings(settings)
    key = expr + "|" + json.dumps(norm, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()[:16]


# ============================================================
# 数据库操作
# ============================================================

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
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
            error TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_results (
            alpha_id TEXT NOT NULL,
            factor_name TEXT,
            check_name TEXT NOT NULL,
            check_result TEXT,
            check_value REAL,
            check_limit REAL,
            checked_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, check_name, checked_at)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS self_corr (
            alpha_id TEXT NOT NULL,
            factor_name TEXT,
            lag_period TEXT,
            correlation REAL,
            max_self_corr REAL,
            min_self_corr REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (alpha_id, lag_period, fetched_at)
        )
    """)
    cursor.execute("""
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
            passed INTEGER,
            error TEXT,
            submitted INTEGER DEFAULT 0,
            submit_result TEXT
        )
    """)
    conn.commit()
    return conn


def alpha_exists(conn: sqlite3.Connection, expr: str, settings: Dict) -> Optional[Dict]:
    h = expr_hash(expr, settings)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM alphas WHERE expr_hash = ?", (h,))
    row = cursor.fetchone()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None


def save_alpha_result(conn: sqlite3.Connection, expr: str, settings: Dict,
                      factor_name: str, alpha_id: Optional[str],
                      status: str, stats: Dict = None, error: str = None):
    h = expr_hash(expr, settings)
    settings_json = json.dumps(normalize_settings(settings), sort_keys=True)
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    existing = alpha_exists(conn, expr, settings)
    if existing:
        updates = []
        params = []
        if alpha_id:
            updates.append("alpha_id = ?")
            params.append(alpha_id)
        if status:
            updates.append("status = ?")
            params.append(status)
        if stats:
            for key in ["sharpe", "fitness", "ic", "rank_ic", "turnover",
                         "annual_return", "max_drawdown"]:
                if key in stats and stats[key] is not None:
                    updates.append(f"{key} = ?")
                    params.append(stats[key])
        if error:
            updates.append("error = ?")
            params.append(error)
        updates.append("completed_at = ?")
        params.append(now)
        params.append(h)
        cursor.execute(f"UPDATE alphas SET {', '.join(updates)} WHERE expr_hash = ?", params)
    else:
        cursor.execute("""
            INSERT INTO alphas
            (expr_hash, expression, factor_name, settings_json, alpha_id,
             status, sharpe, fitness, ic, rank_ic, turnover,
             annual_return, max_drawdown, completed_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            h, expr, factor_name, settings_json, alpha_id, status,
            stats.get("sharpe") if stats else None,
            stats.get("fitness") if stats else None,
            stats.get("ic") if stats else None,
            stats.get("rank_ic") if stats else None,
            stats.get("turnover") if stats else None,
            stats.get("annual_return") if stats else None,
            stats.get("max_drawdown") if stats else None,
            now, error,
        ))
    conn.commit()


def save_self_corr(conn: sqlite3.Connection, alpha_id: str, factor_name: str,
                   self_corr_df, fetched_at: str):
    cursor = conn.cursor()
    max_corr = None
    min_corr = None
    if not self_corr_df.empty:
        if "alpha_max_self_corr" in self_corr_df.columns:
            max_corr = self_corr_df["alpha_max_self_corr"].iloc[0]
        if "alpha_min_self_corr" in self_corr_df.columns:
            min_corr = self_corr_df["alpha_min_self_corr"].iloc[0]
    for _, row in self_corr_df.iterrows():
        lag = str(row.get("period", row.get("lag", "")))
        corr = row.get("correlation", None)
        cursor.execute("""
            INSERT OR REPLACE INTO self_corr
            (alpha_id, factor_name, lag_period, correlation, max_self_corr, min_self_corr, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (alpha_id, factor_name, lag, corr, max_corr, min_corr, fetched_at))
    conn.commit()


def save_submit_check(conn: sqlite3.Connection, alpha_id: str, factor_name: str,
                      status: str, self_corr: Optional[float],
                      sharpe: Optional[float], fitness: Optional[float],
                      turnover: Optional[float], checks_dict: Dict,
                      passed: int, error: str = None):
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO submit_checks
        (alpha_id, factor_name, checked_at, status, self_correlation,
         sharpe, fitness, turnover, checks_json, passed, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        alpha_id, factor_name, now, status, self_corr,
        sharpe, fitness, turnover, json.dumps(checks_dict), passed, error,
    ))
    conn.commit()


def mark_submitted(conn: sqlite3.Connection, alpha_id: str, submit_result: str):
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE submit_checks SET submitted = 1, submit_result = ?
        WHERE alpha_id = ?
    """, (submit_result, alpha_id))
    conn.commit()


# ============================================================
# 提取统计指标
# ============================================================

def extract_stats(result: dict) -> Dict:
    """从ACE库回测结果中提取关键统计指标"""
    stats = {"sharpe": None, "fitness": None, "ic": None, "rank_ic": None,
             "turnover": None, "annual_return": None, "max_drawdown": None}
    # 从is_stats DataFrame提取
    is_stats = result.get("is_stats")
    if is_stats is not None and hasattr(is_stats, 'empty') and not is_stats.empty:
        try:
            row = is_stats.iloc[0]
            for key in ["sharpe", "fitness", "ic", "rankIc", "turnover",
                         "annualReturn", "maxDrawdown"]:
                if key in row:
                    sk = key
                    if key == "rankIc": sk = "rank_ic"
                    elif key == "annualReturn": sk = "annual_return"
                    elif key == "maxDrawdown": sk = "max_drawdown"
                    stats[sk] = row[key]
        except Exception:
            pass
    # 备用：从raw alpha result提取
    if stats["sharpe"] is None:
        alpha_result = result.get("result", result.get("alpha", {}))
        if isinstance(alpha_result, dict):
            is_data = alpha_result.get("is", {})
            if is_data:
                stats["sharpe"] = is_data.get("sharpe", stats["sharpe"])
                stats["fitness"] = is_data.get("fitness", stats["fitness"])
                stats["turnover"] = is_data.get("turnover", stats["turnover"])
    return stats


# ============================================================
# WQB 提交检查客户端
# ============================================================

class WQBCheckClient:
    def __init__(self, session):
        self._session = session
        self._base_url = "https://api.worldquantbrain.com"

    def run_submit_check(self, alpha_id: str, poll: bool = True,
                         max_polls: int = 5, poll_interval: int = 20) -> dict:
        last_result = None
        for poll_idx in range(max_polls if poll else 1):
            data = {}
            try:
                response = self._session.post(f"{self._base_url}/alphas/{alpha_id}/submit")
                if response.status_code in (403, 200, 201, 202):
                    try:
                        data = response.json()
                    except Exception:
                        data = {}
                else:
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                print(f"  提交检查异常: {e}")
                if poll_idx < max_polls - 1:
                    time.sleep(poll_interval)
                    continue
                return {"status": "ERROR", "checks": {}, "error": str(e)}

            result = self._parse_check_result(data)
            last_result = result
            check_count = result["check_count"]
            status = result["status"]
            if poll_idx == 0:
                print(f"  第1次检查: 状态={status}, 检查项数={check_count}")
            else:
                print(f"  第{poll_idx+1}次轮询: 状态={status}, 检查项数={check_count}")
            if check_count >= 5 and status != "PENDING":
                break
            if poll and poll_idx < max_polls - 1:
                print(f"  检查尚未完成，等待 {poll_interval}s 后重试...")
                time.sleep(poll_interval)
        return last_result

    def _parse_check_result(self, data: dict) -> dict:
        is_data = data.get("is", {})
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
            checks_dict[name] = {"status": result, "value": value, "limit": limit}
            if name == "SELF_CORRELATION" and value is not None:
                self_corr_value = float(value)
            elif name == "LOW_SHARPE" and value is not None:
                sharpe = float(value)
            elif name == "LOW_FITNESS" and value is not None:
                fitness = float(value)
            elif name == "LOW_TURNOVER" and value is not None:
                turnover = float(value)
            if result == "FAIL":
                all_pass = False
            elif result == "PENDING":
                has_pending = True
        if has_pending:
            overall_status = "PENDING"
        elif all_pass and checks_dict:
            overall_status = "PASS"
        elif not checks_dict:
            overall_status = "PENDING"
        else:
            overall_status = "FAIL"
        return {
            "status": overall_status, "checks": checks_dict,
            "self_correlation": self_corr_value,
            "sharpe": sharpe, "fitness": fitness, "turnover": turnover,
            "check_count": len(checks_dict),
        }

    def confirm_submit(self, alpha_id: str) -> dict:
        def _do_put():
            return self._session.put(f"{self._base_url}/alphas/{alpha_id}/submit")
        response = _do_put()
        if response.status_code == 201:
            try:
                return response.json()
            except Exception:
                return {"status": "submitted", "code": 201}
        else:
            response.raise_for_status()
            try:
                return response.json()
            except Exception:
                return {}


# ============================================================
# 执行回测
# ============================================================

def run_simulation(session, factors: List[Dict], base_settings: Dict,
                   conn: sqlite3.Connection) -> List[Dict]:
    to_simulate = []
    skipped = []
    for factor in factors:
        factor_settings = dict(base_settings)
        factor_settings.update(factor.get("settings_override", {}))
        existing = alpha_exists(conn, factor["expr"], factor_settings)
        if existing and existing.get("alpha_id") and existing.get("status") == "COMPLETED":
            print(f"  [跳过] {factor['name']}: 已存在 alpha_id={existing['alpha_id']}")
            # 重建结果对象
            skipped.append({
                "alpha_id": existing["alpha_id"],
                "simulate_data": {"regular": factor["expr"]},
                "is_stats": None,
                "factor_name": factor["name"],
            })
            continue
        to_simulate.append(factor)

    if not to_simulate:
        print("  所有因子已回测，无需新建模拟")
        return skipped

    simulate_data_list = []
    for factor in to_simulate:
        factor_settings = dict(base_settings)
        factor_settings.update(factor.get("settings_override", {}))
        sim_data = generate_alpha(
            regular=factor["expr"],
            region=factor_settings.get("region", "USA"),
            universe=factor_settings.get("universe", "TOP3000"),
            delay=factor_settings.get("delay", 1),
            decay=factor_settings.get("decay", 15),
            neutralization=factor_settings.get("neutralization", "SUBINDUSTRY"),
            truncation=factor_settings.get("truncation", 0.08),
            pasteurization=factor_settings.get("pasteurization", "ON"),
            test_period=factor_settings.get("testPeriod", "P1Y6M"),
        )
        simulate_data_list.append(sim_data)

    print(f"\n开始批量回测 {len(simulate_data_list)} 个因子...")
    sim_config = {
        "get_pnl": False, "get_stats": False, "save_pnl_file": False,
        "save_stats_file": False, "save_result_file": False,
        "check_submission": False, "check_self_corr": False, "check_prod_corr": False,
    }
    results = simulate_alpha_list(
        session, simulate_data_list,
        limit_of_concurrent_simulations=1,
        simulation_config=sim_config,
    )

    # 匹配结果（imap_unordered不保序）
    def match_factor(result: dict) -> Optional[str]:
        sd = result.get("simulate_data", {})
        result_expr = sd.get("regular", "")
        for f in to_simulate:
            if f["expr"] == result_expr:
                f_settings = dict(base_settings)
                f_settings.update(f.get("settings_override", {}))
                r_settings = sd.get("settings", {})
                if f_settings.get("neutralization", "SUBINDUSTRY") == r_settings.get("neutralization", "SUBINDUSTRY"):
                    return f["name"]
        return None

    name_to_result = {}
    for result in results:
        name = match_factor(result)
        if name:
            name_to_result[name] = result

    saved_results = []
    for factor in to_simulate:
        result = name_to_result.get(factor["name"], {"alpha_id": None})
        alpha_id = result.get("alpha_id")
        if alpha_id:
            factor_settings = dict(base_settings)
            factor_settings.update(factor.get("settings_override", {}))
            stats = extract_stats(result)
            save_alpha_result(conn, factor["expr"], factor_settings,
                              factor["name"], alpha_id, "COMPLETED", stats)
            print(f"  [完成] {factor['name']}: alpha_id={alpha_id}, "
                  f"Sharpe={stats.get('sharpe')}, Fitness={stats.get('fitness')}")
            saved_results.append(result)
        else:
            factor_settings = dict(base_settings)
            factor_settings.update(factor.get("settings_override", {}))
            save_alpha_result(conn, factor["expr"], factor_settings,
                              factor["name"], None, "FAILED",
                              error=result.get("error", "回测失败"))
            print(f"  [失败] {factor['name']}: 回测未完成")

    saved_results.extend(skipped)
    return saved_results


def check_self_corr_for_factor(session, alpha_id: str, factor_name: str,
                                conn: sqlite3.Connection) -> Dict:
    print(f"  检查自相关: {factor_name} ({alpha_id})")
    try:
        sc_df = get_self_corr(session, alpha_id)
        if sc_df is not None and not sc_df.empty:
            fetched_at = datetime.now().isoformat()
            save_self_corr(conn, alpha_id, factor_name, sc_df, fetched_at)
            max_sc = sc_df["alpha_max_self_corr"].iloc[0]
            passed = max_sc < 0.7
            print(f"    自相关={max_sc:.4f}, 结果={'✅' if passed else '❌'}")
            return {"self_correlation": max_sc, "result": "PASS" if passed else "FAIL"}
        else:
            print(f"    自相关数据为空")
            return {"self_correlation": None, "result": "NONE"}
    except Exception as e:
        print(f"    自相关检查异常: {e}")
        return {"self_correlation": None, "result": "ERROR", "error": str(e)}


def run_submission_check(session, alpha_id: str, factor_name: str,
                          conn: sqlite3.Connection) -> Dict:
    print(f"\n  执行提交检查: {factor_name} ({alpha_id})")
    client = WQBCheckClient(session)
    try:
        result = client.run_submit_check(alpha_id, poll=True, max_polls=5, poll_interval=20)
    except Exception as e:
        print(f"  提交检查异常: {e}")
        return {"status": "ERROR", "error": str(e)}
    if result is None:
        return {"status": "ERROR", "error": "无返回结果"}

    checks = result.get("checks", {})
    check_count = len(checks)
    failed_checks = [k for k, v in checks.items() if v.get("status") == "FAIL"]
    pending_checks = [k for k, v in checks.items() if v.get("status") == "PENDING"]
    all_pass = len(failed_checks) == 0 and len(pending_checks) == 0

    checked_at = datetime.now().isoformat()
    save_submit_check(conn, alpha_id, factor_name, result["status"],
                      result.get("self_correlation"), result.get("sharpe"),
                      result.get("fitness"), result.get("turnover"),
                      checks, 1 if all_pass else 0, error=result.get("error"))

    print(f"    检查项数: {check_count}, 通过: {all_pass}")
    for name, check in sorted(checks.items()):
        status_str = check.get("status", "?")
        value = check.get("value")
        details = f" (value={value})" if value is not None else ""
        print(f"      {name}: {status_str}{details}")

    return {
        "status": result["status"], "checks": checks,
        "check_count": check_count, "all_pass": all_pass,
        "self_correlation": result.get("self_correlation"),
        "sharpe": result.get("sharpe"), "fitness": result.get("fitness"),
        "turnover": result.get("turnover"),
        "failed_checks": failed_checks, "pending_checks": pending_checks,
    }


def confirm_alpha_submit(session, alpha_id: str, factor_name: str,
                          conn: sqlite3.Connection) -> bool:
    print(f"\n  正式提交: {factor_name} ({alpha_id})")
    client = WQBCheckClient(session)
    try:
        result = client.confirm_submit(alpha_id)
        mark_submitted(conn, alpha_id, json.dumps(result))
        print(f"    提交成功！")
        return True
    except Exception as e:
        print(f"    提交失败: {e}")
        return False


# ============================================================
# 报告生成
# ============================================================

def generate_report(report_path: str, conn: sqlite3.Connection,
                    phase1_results: List[Dict], phase2_results: List[Dict],
                    phase3_results: List[Dict], passed_for_submit: List[Dict],
                    submitted_factors: List[Dict]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# WQB d5自相关低谷突破 - 提交检查报告 (v2)\n")
    lines.append(f"**生成时间**: {now}\n")
    lines.append("---\n")
    lines.append("## 执行摘要\n")
    phase1_ok = sum(1 for r in phase1_results if r.get("alpha_id"))
    phase2_ok = sum(1 for r in phase2_results if r.get("alpha_id"))
    passed_check = len(passed_for_submit)
    submitted_ok = len(submitted_factors)
    lines.append(f"- 阶段1 (vol20权重精调, decay=0): {phase1_ok}/{len(phase1_results)} 个回测成功")
    lines.append(f"- 阶段2 (d5协同信号): {phase2_ok}/{len(phase2_results)} 个回测成功")
    lines.append(f"- 阶段3 (提交检查): {passed_check} 个因子通过全部检查")
    lines.append(f"- 正式提交: {submitted_ok} 个因子成功提交\n")

    lines.append("## 阶段1: vol20权重精调 (decay=0)\n")
    lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关 | 状态 |")
    lines.append("|----------|----------|--------|---------|--------|--------|------|")
    for r in phase1_results:
        aid = r.get("alpha_id", "-") or "-"
        stats = r.get("stats", {})
        sc = r.get("self_correlation")
        sc_str = f"{sc:.4f}" if sc is not None else "-"
        status = "✅" if r.get("passed") else "❌"
        lines.append(f"| {r.get('name', '-')} | {aid} | {stats.get('sharpe', '-')} | "
                     f"{stats.get('fitness', '-')} | {stats.get('turnover', '-')} | "
                     f"{sc_str} | {status} |")

    lines.append("\n## 阶段2: d5协同信号\n")
    lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 换手率 | 自相关 | 状态 |")
    lines.append("|----------|----------|--------|---------|--------|--------|------|")
    for r in phase2_results:
        aid = r.get("alpha_id", "-") or "-"
        stats = r.get("stats", {})
        sc = r.get("self_correlation")
        sc_str = f"{sc:.4f}" if sc is not None else "-"
        status = "✅" if r.get("passed") else "❌"
        lines.append(f"| {r.get('name', '-')} | {aid} | {stats.get('sharpe', '-')} | "
                     f"{stats.get('fitness', '-')} | {stats.get('turnover', '-')} | "
                     f"{sc_str} | {status} |")

    lines.append("\n## 阶段3: 提交检查结果\n")
    if phase3_results:
        for pr in phase3_results:
            lines.append(f"\n### {pr.get('factor_name', '-')} ({pr.get('alpha_id', '-')})\n")
            lines.append(f"- **状态**: {pr.get('status', '-')}")
            lines.append(f"- **自相关**: {pr.get('self_correlation', '-')}")
            lines.append(f"- **检查项数**: {pr.get('check_count', 0)}/8")
            lines.append(f"- **失败项**: {', '.join(pr.get('failed_checks', [])) or '无'}\n")
            lines.append("| 检查项 | 结果 | 数值 | 阈值 |")
            lines.append("|--------|------|------|------|")
            for name, check in sorted(pr.get('checks', {}).items()):
                status_str = check.get("status", "?")
                value = check.get("value", "-")
                limit = check.get("limit", "-")
                value_str = f"{value:.4f}" if isinstance(value, float) else str(value) if value is not None else "-"
                limit_str = f"{limit:.4f}" if isinstance(limit, float) else str(limit) if limit is not None else "-"
                lines.append(f"| {name} | {status_str} | {value_str} | {limit_str} |")
    else:
        lines.append("\n无因子满足提交检查条件。\n")

    lines.append("\n## 正式提交结果\n")
    if submitted_factors:
        lines.append("| 因子名称 | Alpha ID | 提交状态 |")
        lines.append("|----------|----------|----------|")
        for sf in submitted_factors:
            lines.append(f"| {sf.get('factor_name', '-')} | {sf.get('alpha_id', '-')} | ✅ 已提交 |")
    else:
        lines.append("\n无因子通过全部检查，未执行正式提交。\n")

    lines.append("\n## 结论与建议\n")
    if passed_for_submit:
        lines.append("### 通过检查的因子\n")
        for pf in passed_for_submit:
            lines.append(f"- ✅ **{pf.get('factor_name', '-')}** ({pf.get('alpha_id', '-')}): "
                        f"Sharpe={pf.get('sharpe')}, Fitness={pf.get('fitness')}, "
                        f"SC={pf.get('self_correlation')}")
    lines.append("\n### 核心发现\n")
    lines.append("1. d5自相关低谷 (SC=0.5838) 仅存在于decay=15设置下")
    lines.append("2. decay=0时，d5自身SC≈0.71，加入vol20后SC仍在0.71-0.72")
    lines.append("3. vol20权重对SC影响极小（0.5%~2%权重SC几乎不变）")
    lines.append("4. 唯一SC<0.7的是乘法组合，但Fitness过低\n")
    lines.append("### 下一步建议\n")
    lines.append("1. 尝试d5 (decay=15) + 超低权重的其他低SC信号")
    lines.append("2. 探索其他非vol20的协同信号（如fundamental数据）")
    lines.append("3. 使用decay=15但将vol20也改为decay形式")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n报告已生成: {report_path}")


# ============================================================
# 主流程
# ============================================================

async def main():
    result_mode = sys.argv[1] if len(sys.argv) > 1 else "display_only"
    email = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
    password = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")
    db_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(OUTPUT_DIR, "wqb_state.db")
    report_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(OUTPUT_DIR, "wqb_d5_breakthrough_submit_report.md")

    print(f"[参数] result_mode={result_mode}")
    print(f"[参数] db_path={db_path}")
    print(f"[参数] report_path={report_path}")

    sdk = None
    try:
        from codeact_sdk import CodeActSDK
        sdk = CodeActSDK()
    except ImportError:
        pass

    os.environ["BRAIN_CREDENTIAL_EMAIL"] = email
    os.environ["BRAIN_CREDENTIAL_PASSWORD"] = password

    try:
        conn = init_db(db_path)
        print(f"数据库已初始化: {db_path}")

        print("\n登录 WQB...")
        session = start_session()
        print("登录成功！")

        # ============================================================
        # 阶段1: vol20权重精调 (decay=0)
        # ============================================================
        print("\n" + "=" * 60)
        print("阶段1: vol20权重精调 (4个因子, decay=0)")
        print("=" * 60)

        phase1_settings = dict(DEFAULT_SETTINGS)
        phase1_results = run_simulation(session, PHASE1_FACTORS, phase1_settings, conn)

        phase1_enhanced = []
        for r in phase1_results:
            aid = r.get("alpha_id")
            if aid:
                fname = r.get("factor_name", "")
                if not fname:
                    sd = r.get("simulate_data", {})
                    expr = sd.get("regular", "")
                    for f in PHASE1_FACTORS:
                        if f["expr"] == expr:
                            fname = f["name"]
                            break
                if not fname:
                    fname = aid

                # 检查已有自相关
                cursor = conn.cursor()
                cursor.execute("SELECT max_self_corr FROM self_corr WHERE alpha_id = ? ORDER BY fetched_at DESC LIMIT 1", (aid,))
                existing_sc = cursor.fetchone()
                if existing_sc and existing_sc[0] is not None:
                    print(f"  [跳过自相关] {fname} ({aid}): 已有记录 SC={existing_sc[0]}")
                    sc_result = {"self_correlation": existing_sc[0], "result": "PASS" if existing_sc[0] < 0.7 else "FAIL"}
                else:
                    time.sleep(SUBMIT_INTERVAL)
                    sc_result = check_self_corr_for_factor(session, aid, fname, conn)

                stats = extract_stats(r)
                sharpe = stats.get("sharpe", 0) or 0
                fitness = stats.get("fitness", 0) or 0
                sc_val = sc_result.get("self_correlation")
                passed = (sc_val is not None and sc_val < 0.7 and sharpe >= 1.25 and fitness >= 1.0)
                phase1_enhanced.append({
                    "name": fname, "alpha_id": aid, "stats": stats,
                    "self_correlation": sc_val, "passed": passed,
                })
                print(f"  [{('✅' if passed else '❌')}] {fname}: S={sharpe:.2f}, F={fitness:.2f}, SC={sc_val}")

        # ============================================================
        # 阶段2: d5协同信号
        # ============================================================
        print("\n" + "=" * 60)
        print("阶段2: d5+其他协同信号 (3个因子)")
        print("=" * 60)

        phase2_settings = dict(DEFAULT_SETTINGS)
        phase2_results = run_simulation(session, PHASE2_FACTORS, phase2_settings, conn)

        phase2_enhanced = []
        for r in phase2_results:
            aid = r.get("alpha_id")
            if aid:
                fname = r.get("factor_name", "")
                if not fname:
                    sd = r.get("simulate_data", {})
                    expr = sd.get("regular", "")
                    for f in PHASE2_FACTORS:
                        if f["expr"] == expr:
                            fname = f["name"]
                            break
                if not fname:
                    fname = aid

                cursor = conn.cursor()
                cursor.execute("SELECT max_self_corr FROM self_corr WHERE alpha_id = ? ORDER BY fetched_at DESC LIMIT 1", (aid,))
                existing_sc = cursor.fetchone()
                if existing_sc and existing_sc[0] is not None:
                    print(f"  [跳过自相关] {fname} ({aid}): 已有记录 SC={existing_sc[0]}")
                    sc_result = {"self_correlation": existing_sc[0], "result": "PASS" if existing_sc[0] < 0.7 else "FAIL"}
                else:
                    time.sleep(SUBMIT_INTERVAL)
                    sc_result = check_self_corr_for_factor(session, aid, fname, conn)

                stats = extract_stats(r)
                sharpe = stats.get("sharpe", 0) or 0
                fitness = stats.get("fitness", 0) or 0
                sc_val = sc_result.get("self_correlation")
                passed = (sc_val is not None and sc_val < 0.7 and sharpe >= 1.25 and fitness >= 1.0)
                phase2_enhanced.append({
                    "name": fname, "alpha_id": aid, "stats": stats,
                    "self_correlation": sc_val, "passed": passed,
                })
                print(f"  [{('✅' if passed else '❌')}] {fname}: S={sharpe:.2f}, F={fitness:.2f}, SC={sc_val}")

        # ============================================================
        # 阶段3: 提交检查
        # ============================================================
        print("\n" + "=" * 60)
        print("阶段3: 提交检查")
        print("=" * 60)

        candidates = []
        for r in phase1_enhanced + phase2_enhanced:
            stats = r.get("stats", {})
            sharpe = stats.get("sharpe", 0) or 0
            fitness = stats.get("fitness", 0) or 0
            if sharpe >= 1.25 and fitness >= 1.0:
                candidates.append({
                    "alpha_id": r["alpha_id"], "factor_name": r["name"],
                    "sharpe": sharpe, "fitness": fitness,
                    "self_correlation": r.get("self_correlation"),
                })
                print(f"  [候选] {r['name']} ({r['alpha_id']}): S={sharpe:.2f}, F={fitness:.2f}, SC={r.get('self_correlation')}")

        phase3_results = []
        passed_for_submit = []
        submitted_factors = []

        for candidate in candidates:
            alpha_id = candidate["alpha_id"]
            factor_name = candidate["factor_name"]
            cursor = conn.cursor()
            cursor.execute("SELECT status, passed, submitted FROM submit_checks WHERE alpha_id = ? ORDER BY checked_at DESC LIMIT 1", (alpha_id,))
            existing_check = cursor.fetchone()
            if existing_check:
                existing_status = existing_check[0]
                existing_passed = existing_check[1]
                existing_submitted = existing_check[2]
                print(f"\n  [跳过检查] {factor_name} ({alpha_id}): 已有检查记录 status={existing_status}")
                if existing_submitted:
                    submitted_factors.append(candidate)
                    continue
                if existing_passed:
                    passed_for_submit.append(candidate)
                    time.sleep(SUBMIT_INTERVAL)
                    if confirm_alpha_submit(session, alpha_id, factor_name, conn):
                        submitted_factors.append(candidate)
                        passed_for_submit = [p for p in passed_for_submit if p["alpha_id"] != alpha_id]
                    continue
                continue

            time.sleep(SUBMIT_INTERVAL)
            check_result = run_submission_check(session, alpha_id, factor_name, conn)
            phase3_results.append({
                "alpha_id": alpha_id, "factor_name": factor_name,
                "status": check_result.get("status"),
                "checks": check_result.get("checks", {}),
                "check_count": check_result.get("check_count", 0),
                "all_pass": check_result.get("all_pass", False),
                "self_correlation": check_result.get("self_correlation"),
                "sharpe": check_result.get("sharpe"),
                "fitness": check_result.get("fitness"),
                "turnover": check_result.get("turnover"),
                "failed_checks": check_result.get("failed_checks", []),
                "pending_checks": check_result.get("pending_checks", []),
            })
            if check_result.get("all_pass"):
                passed_for_submit.append(candidate)
                print(f"\n  ✅ {factor_name} 通过全部8项检查，准备正式提交...")
                time.sleep(SUBMIT_INTERVAL)
                if confirm_alpha_submit(session, alpha_id, factor_name, conn):
                    submitted_factors.append(candidate)
                    passed_for_submit = [p for p in passed_for_submit if p["alpha_id"] != alpha_id]
            else:
                print(f"\n  ❌ {factor_name} 未通过检查")

        # ============================================================
        # 生成报告
        # ============================================================
        print("\n" + "=" * 60)
        print("生成报告")
        print("=" * 60)
        generate_report(report_path, conn, phase1_enhanced, phase2_enhanced,
                        phase3_results, passed_for_submit, submitted_factors)
        conn.close()

        # 构建摘要
        summary_lines = []
        summary_lines.append(f"## d5突破提交报告 (v2)\n")
        summary_lines.append(f"**阶段1**: {len(phase1_enhanced)}个vol20权重因子 (decay=0)")
        summary_lines.append(f"**阶段2**: {len(phase2_enhanced)}个d5协同因子")
        summary_lines.append(f"**提交检查**: {len(phase3_results)}个因子执行检查")
        summary_lines.append(f"**全部通过**: {len(passed_for_submit)}个因子")
        summary_lines.append(f"**正式提交**: {len(submitted_factors)}个因子\n")
        if submitted_factors:
            summary_lines.append("**已提交因子**:")
            for sf in submitted_factors:
                summary_lines.append(f"  - {sf.get('factor_name')} ({sf.get('alpha_id')})")
        if passed_for_submit:
            summary_lines.append("\n**待提交因子**:")
            for pf in passed_for_submit:
                summary_lines.append(f"  - {pf.get('factor_name')} ({pf.get('alpha_id')})")
        abs_report_path = os.path.abspath(report_path)
        summary_lines.append(f"\n[完整报告](computer://{abs_report_path})")
        message = "\n".join(summary_lines)
        actual_mode = result_mode if result_mode != "auto" else "display_only"

        if sdk:
            await sdk.submit_result(
                result_mode=actual_mode, status="success", message=message,
                data={"report_path": report_path, "phase1_count": len(phase1_enhanced),
                      "phase2_count": len(phase2_enhanced), "phase3_count": len(phase3_results),
                      "passed_count": len(passed_for_submit), "submitted_count": len(submitted_factors)},
            )
        else:
            print("\n结果摘要:\n" + message)

    except Exception as e:
        print(f"\n执行失败: {e}")
        import traceback
        traceback.print_exc()
        if sdk:
            await sdk.submit_result(
                result_mode="notify", status="error",
                message=f"执行失败: {e}", data={"error_type": type(e).__name__},
            )


if __name__ == "__main__":
    asyncio.run(main())