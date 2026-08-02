#!/usr/bin/env python3
"""
ACE Batch Runner - Unified batch factor backtest + submission check script

Features:
- Input: list of factor expressions
- Batch backtest with multi-simulation (10 per batch, 3 concurrent batches)
- Auto-check 8 submission items
- Auto-check self-correlation
- Auto-check production correlation
- Output results table
- Write results to wqb_state.db
- Auto-submit factors that pass all checks
"""

import os
import sys
import json
import time
import sqlite3
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

# Set credentials via environment variables before importing ace_lib
os.environ.setdefault("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
os.environ.setdefault("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")

# Add ace_lib to path
_ACE_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ace_lib")
sys.path.insert(0, _ACE_LIB_DIR)

import pandas as pd
import requests

import ace_lib
from helpful_functions import prettify_result


# ============================================================
# Constants
# ============================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
OUTPUT_DIR = os.path.normpath(OUTPUT_DIR)
DB_PATH = os.path.join(OUTPUT_DIR, "wqb_state.db")

DEFAULT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "INDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "testPeriod": "P0Y0M0D",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "maxTrade": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}

# 8 submission check items (standard set)
SUBMISSION_CHECK_ITEMS = [
    "LOW_SHARPE",
    "LOW_FITNESS",
    "LOW_TURNOVER",
    "HIGH_TURNOVER",
    "CONCENTRATED_WEIGHT",
    "LOW_SUB_UNIVERSE_SHARPE",
    "SELF_CORRELATION",
    "MATCHES_COMPETITION",
]


# ============================================================
# Database helpers
# ============================================================

def compute_expr_hash(expression: str, settings: dict) -> str:
    """Compute a hash of expression + normalized settings."""
    # Normalize settings: use sorted keys
    settings_normalized = json.dumps(settings, sort_keys=True)
    combined = f"{expression}|{settings_normalized}"
    return hashlib.md5(combined.encode()).hexdigest()


def ensure_db(db_path: str):
    """Ensure database tables exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    
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
            error TEXT,
            progress_url TEXT
        )
    """)
    
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
            submitted INTEGER DEFAULT 0,
            submit_result TEXT,
            error TEXT
        )
    """)
    
    conn.commit()
    conn.close()


def upsert_alpha(db_path: str, expr_hash: str, expression: str, factor_name: str,
                 settings: dict, alpha_id: str = None, status: str = "PENDING",
                 sharpe: float = None, fitness: float = None, turnover: float = None,
                 is_summary: dict = None, error: str = None):
    """Insert or update alpha record."""
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    
    settings_json = json.dumps(settings, sort_keys=True)
    is_summary_json = json.dumps(is_summary) if is_summary else None
    
    existing = conn.execute(
        "SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)
    ).fetchone()
    
    if existing:
        conn.execute("""
            UPDATE alphas SET
                alpha_id = COALESCE(?, alpha_id),
                status = ?,
                sharpe = COALESCE(?, sharpe),
                fitness = COALESCE(?, fitness),
                turnover = COALESCE(?, turnover),
                is_summary = COALESCE(?, is_summary),
                completed_at = ?,
                error = ?
            WHERE expr_hash = ?
        """, (alpha_id, status, sharpe, fitness, turnover, is_summary_json, now, error, expr_hash))
    else:
        conn.execute("""
            INSERT INTO alphas 
            (expr_hash, expression, factor_name, settings_json, alpha_id, status, 
             sharpe, fitness, turnover, is_summary, submitted_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (expr_hash, expression, factor_name, settings_json, alpha_id, status,
              sharpe, fitness, turnover, is_summary_json, now, error))
    
    conn.commit()
    conn.close()


def upsert_submit_check(db_path: str, alpha_id: str, factor_name: str,
                        status: str, self_correlation: float = None,
                        sharpe: float = None, fitness: float = None,
                        turnover: float = None, checks: dict = None,
                        passed: int = 0, submitted: int = 0,
                        submit_result: str = None, error: str = None):
    """Insert or update submission check record."""
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    
    checks_json = json.dumps(checks) if checks else None
    
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
                passed = ?,
                submitted = ?,
                submit_result = COALESCE(?, submit_result),
                error = ?
            WHERE alpha_id = ?
        """, (factor_name, now, status, self_correlation, sharpe, fitness, turnover,
              checks_json, passed, submitted, submit_result, error, alpha_id))
    else:
        conn.execute("""
            INSERT INTO submit_checks
            (alpha_id, factor_name, checked_at, status, self_correlation, 
             sharpe, fitness, turnover, checks_json, passed, submitted, submit_result, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (alpha_id, factor_name, now, status, self_correlation, sharpe, fitness,
              turnover, checks_json, passed, submitted, submit_result, error))
    
    conn.commit()
    conn.close()


def get_alpha_by_id(db_path: str, alpha_id: str) -> dict:
    """Get alpha record by alpha_id."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT expr_hash, expression, factor_name, settings_json, sharpe, fitness, turnover FROM alphas WHERE alpha_id = ?",
        (alpha_id,)
    ).fetchone()
    conn.close()
    
    if row:
        return {
            "expr_hash": row[0],
            "expression": row[1],
            "factor_name": row[2],
            "settings": json.loads(row[3]) if row[3] else {},
            "sharpe": row[4],
            "fitness": row[5],
            "turnover": row[6],
        }
    return None


# ============================================================
# Submission check (using direct API call not in ACE lib)
# ============================================================

def run_submit_check(s: ace_lib.SingleSession, alpha_id: str) -> dict:
    """
    Run submission check via POST /alphas/{id}/submit
    
    Returns dict with:
      - status: PASS / FAIL / PENDING
      - checks: {name: {status, value, limit}}
      - self_correlation: float or None
      - sharpe: float or None
      - fitness: float or None
      - turnover: float or None
    """
    url = f"{ace_lib.brain_api_url}/alphas/{alpha_id}/submit"
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = s.post(url)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                raise
    
    # 403 is normal (checks not passed), 200/201/202 = all passed or processing
    if response.status_code in (403, 200, 201, 202):
        try:
            data = response.json()
        except Exception:
            data = {}
    else:
        response.raise_for_status()
        data = response.json()
    
    # Parse IS stats
    is_data = data.get("is", {})
    
    # Parse checks
    checks_list = is_data.get("checks", [])
    checks_dict = {}
    all_pass = True
    has_pending = False
    self_corr_value = None
    sharpe_val = None
    fitness_val = None
    turnover_val = None
    
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
        
        # Extract key metrics from checks
        if name == "SELF_CORRELATION" and value is not None:
            self_corr_value = float(value)
        elif name == "LOW_SHARPE" and value is not None:
            sharpe_val = float(value)
        elif name == "LOW_FITNESS" and value is not None:
            fitness_val = float(value)
        elif name == "LOW_TURNOVER" and value is not None:
            turnover_val = float(value)
        
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
        "sharpe": sharpe_val,
        "fitness": fitness_val,
        "turnover": turnover_val,
    }


def confirm_submit(s: ace_lib.SingleSession, alpha_id: str) -> dict:
    """
    Confirm final submission via PUT /alphas/{id}/submit
    """
    url = f"{ace_lib.brain_api_url}/alphas/{alpha_id}/submit"
    response = s.put(url)
    response.raise_for_status()
    return response.json()


# ============================================================
# Production correlation check
# ============================================================

def check_production_correlation(s: ace_lib.SingleSession, alpha_id: str, 
                               threshold: float = 0.7) -> dict:
    """
    Check production correlation for an alpha.
    
    Returns:
      dict with status, value, threshold
    """
    try:
        result_df = ace_lib.check_prod_corr_test(s, alpha_id, threshold=threshold)
        if result_df.empty:
            return {"status": "NONE", "value": None, "threshold": threshold}
        
        row = result_df.iloc[0]
        return {
            "status": row.get("result", "UNKNOWN"),
            "value": row.get("value"),
            "threshold": threshold,
        }
    except Exception as e:
        return {"status": "ERROR", "value": None, "threshold": threshold, "error": str(e)}


# ============================================================
# Core batch runner
# ============================================================

class ACEBatchRunner:
    """
    Unified batch factor backtest + submission check runner using ACE library.
    """
    
    def __init__(self, db_path: str = DB_PATH, 
                 batch_size: int = 10,
                 concurrency: int = 3,
                 auto_submit: bool = False,
                 prod_corr_threshold: float = 0.7,
                 settings: dict = None):
        self.db_path = db_path
        self.batch_size = min(max(batch_size, 2), 10)  # ACE multi-sim limit 2-10
        self.concurrency = min(max(concurrency, 1), 8)  # ACE concurrent limit 1-8
        self.auto_submit = auto_submit
        self.prod_corr_threshold = prod_corr_threshold
        self.settings = settings or DEFAULT_SETTINGS.copy()
        
        ensure_db(db_path)
        self.session = None
    
    def login(self):
        """Login to WQB platform."""
        print("[ACE] 登录中...")
        self.session = ace_lib.start_session()
        timeout = ace_lib.check_session_timeout(self.session)
        print(f"[ACE] 登录成功，会话有效期: {timeout/3600:.1f} 小时")
        return self.session
    
    def build_alpha_list(self, expressions: list, factor_names: list = None) -> list:
        """
        Build list of alpha simulation data from expressions.
        
        Args:
            expressions: list of factor expression strings
            factor_names: optional list of factor names (same length as expressions)
            
        Returns:
            list of simulation_data dicts, and list of (expr, name) tuples
        """
        alpha_list = []
        name_map = {}
        
        for i, expr in enumerate(expressions):
            name = factor_names[i] if factor_names and i < len(factor_names) else f"factor_{i+1}"
            
            sim_data = ace_lib.generate_alpha(
                regular=expr,
                alpha_type="REGULAR",
                region=self.settings.get("region", "USA"),
                universe=self.settings.get("universe", "TOP3000"),
                delay=self.settings.get("delay", 1),
                decay=self.settings.get("decay", 0),
                neutralization=self.settings.get("neutralization", "INDUSTRY"),
                truncation=self.settings.get("truncation", 0.08),
                pasteurization=self.settings.get("pasteurization", "ON"),
            )
            
            alpha_list.append(sim_data)
            name_map[expr] = name
        
        return alpha_list, name_map
    
    def batch_simulate(self, alpha_list: list) -> list:
        """
        Run batch simulation using ACE's multi-simulation with concurrent batches.
        
        Returns:
            list of result dicts from simulate_multi_alpha style
        """
        print(f"[ACE] 开始批量回测，共 {len(alpha_list)} 个因子")
        print(f"[ACE] 每批 {self.batch_size} 个，并发 {self.concurrency} 批")
        
        results = ace_lib.simulate_alpha_list_multi(
            self.session,
            alpha_list,
            limit_of_concurrent_simulations=self.concurrency,
            limit_of_multi_simulations=self.batch_size,
            simulation_config=ace_lib.DEFAULT_CONFIG,
        )
        
        success_count = sum(1 for r in results if r["alpha_id"] is not None)
        print(f"[ACE] 回测完成: 成功 {success_count}/{len(alpha_list)} 个")
        
        return results
    
    def check_existing_alphas(self, alpha_ids: list, factor_names: list = None) -> list:
        """
        Run submission checks on existing alpha_ids (no re-simulation).
        
        Args:
            alpha_ids: list of existing alpha IDs
            factor_names: optional list of factor names
            
        Returns:
            list of result dicts with submission check info
        """
        print(f"[ACE] 检查已有 {len(alpha_ids)} 个因子的提交状态...")
        
        results = []
        for i, alpha_id in enumerate(alpha_ids):
            factor_name = factor_names[i] if factor_names and i < len(factor_names) else f"alpha_{i+1}"
            
            # Build a minimal result dict
            result = {
                "alpha_id": alpha_id,
                "factor_name": factor_name,
                "simulate_data": {"regular": "", "type": "REGULAR", "settings": self.settings},
            }
            results.append(result)
        
        # Create name_map for the check function
        name_map = {}
        for r in results:
            name_map[r["simulate_data"].get("regular", "")] = r["factor_name"]
        
        # Use the existing submission check method
        checked = self.run_submission_checks(results, name_map)
        return checked
    
    def run_submission_checks(self, results: list, name_map: dict = None) -> list:
        """
        Run submission checks for all successfully simulated alphas.
        
        Args:
            results: list of result dicts from simulation
            name_map: dict mapping expression -> factor_name
            
        Returns:
            list of enhanced result dicts with submission check info
        """
        print(f"\n[ACE] 开始提交检查...")
        
        enhanced = []
        checked = 0
        
        for result in results:
            alpha_id = result["alpha_id"]
            if alpha_id is None:
                enhanced.append(result)
                continue
            
            # Always get expression for DB operations
            expr = result["simulate_data"].get("regular", "")
            
            # Prefer factor_name from result dict, fall back to name_map lookup
            factor_name = result.get("factor_name")
            if not factor_name:
                factor_name = name_map.get(expr, "unknown") if name_map else "unknown"
            
            print(f"  检查 {factor_name} ({alpha_id})...", end=" ")
            
            try:
                check_result = run_submit_check(self.session, alpha_id)
                
                # Also get production correlation
                prod_corr = check_production_correlation(
                    self.session, alpha_id, threshold=self.prod_corr_threshold
                )
                
                result["submit_check"] = check_result
                result["prod_corr"] = prod_corr
                result["factor_name"] = factor_name
                
                # Save to DB
                passed = 1 if check_result["status"] == "PASS" else 0
                upsert_submit_check(
                    self.db_path,
                    alpha_id=alpha_id,
                    factor_name=factor_name,
                    status=check_result["status"],
                    self_correlation=check_result["self_correlation"],
                    sharpe=check_result["sharpe"],
                    fitness=check_result["fitness"],
                    turnover=check_result["turnover"],
                    checks=check_result["checks"],
                    passed=passed,
                )
                
                # Update alpha table
                expr_hash = compute_expr_hash(expr, self.settings)
                upsert_alpha(
                    self.db_path,
                    expr_hash=expr_hash,
                    expression=expr,
                    factor_name=factor_name,
                    settings=self.settings,
                    alpha_id=alpha_id,
                    status="COMPLETED",
                    sharpe=check_result.get("sharpe"),
                    fitness=check_result.get("fitness"),
                    turnover=check_result.get("turnover"),
                    is_summary=check_result["checks"],
                )
                
                checked += 1
                print(f"{check_result['status']}")
                
            except Exception as e:
                print(f"ERROR: {e}")
                result["submit_check"] = {"status": "ERROR", "error": str(e)}
                result["factor_name"] = factor_name
                enhanced.append(result)
                continue
            
            enhanced.append(result)
        
        print(f"[ACE] 提交检查完成: 已检查 {checked} 个")
        return enhanced
    
    def auto_submit_passing(self, results: list) -> list:
        """
        Auto-submit factors that pass all checks.
        
        Returns:
            list of submitted alpha dicts
        """
        if not self.auto_submit:
            return []
        
        submitted = []
        passing = [r for r in results 
                  if r.get("submit_check", {}).get("status") == "PASS"]
        
        if not passing:
            print(f"\n[ACE] 没有通过全部检查的因子，跳过自动提交")
            return []
        
        print(f"\n[ACE] 开始自动提交 {len(passing)} 个通过检查的因子...")
        
        for result in passing:
            alpha_id = result["alpha_id"]
            factor_name = result.get("factor_name", "unknown")
            print(f"  提交 {factor_name} ({alpha_id})...", end=" ")
            
            try:
                submit_result = confirm_submit(self.session, alpha_id)
                
                # Update DB
                upsert_submit_check(
                    self.db_path,
                    alpha_id=alpha_id,
                    factor_name=factor_name,
                    status=result["submit_check"]["status"],
                    self_correlation=result["submit_check"].get("self_correlation"),
                    sharpe=result["submit_check"].get("sharpe"),
                    fitness=result["submit_check"].get("fitness"),
                    turnover=result["submit_check"].get("turnover"),
                    checks=result["submit_check"]["checks"],
                    passed=1,
                    submitted=1,
                    submit_result=json.dumps(submit_result),
                )
                
                submitted.append({
                    "alpha_id": alpha_id,
                    "factor_name": factor_name,
                    "submit_result": submit_result,
                })
                print("✓ 成功")
                
                # Rate limit spacing
                time.sleep(5)  # Small delay between submissions
                
            except Exception as e:
                    print(f"✗ 失败: {e}")
                    upsert_submit_check(
                        self.db_path,
                        alpha_id=alpha_id,
                        factor_name=factor_name,
                        status="SUBMIT_ERROR",
                        error=str(e),
                    )
        
        print(f"[ACE] 自动提交完成: 成功 {len(submitted)}/{len(passing)} 个")
        return submitted
    
    def run(self, expressions: list, factor_names: list = None) -> dict:
        """
        Run the full batch pipeline: simulate -> check -> (auto-submit.
        
        Args:
            expressions: list of factor expression strings
            factor_names: optional list of factor names
            
        Returns:
            dict with results, summary, and submitted list
        """
        if self.session is None:
            self.login()
        
        # Build alpha list
        alpha_list, name_map = self.build_alpha_list(expressions, factor_names)
        
        # Run simulation
        sim_results = self.batch_simulate(alpha_list)
        
        # Run submission checks
        checked_results = self.run_submission_checks(sim_results, name_map)
        
        # Auto-submit passing factors
        submitted = self.auto_submit_passing(checked_results)
        
        # Generate summary
        summary = self.generate_summary(checked_results, submitted)
        
        return {
            "results": checked_results,
            "submitted": submitted,
            "summary": summary,
        }
    
    def generate_summary(self, results: list, submitted: list) -> dict:
        """Generate summary statistics."""
        total = len(results)
        successful = sum(1 for r in results if r["alpha_id"] is not None)
        failed_sim = total - successful
        
        checked = [r for r in results if r.get("submit_check")]
        pass_count = sum(1 for r in checked if r["submit_check"]["status"] == "PASS")
        fail_count = sum(1 for r in checked if r["submit_check"]["status"] == "FAIL")
        pending_count = sum(1 for r in checked if r["submit_check"]["status"] == "PENDING")
        
        return {
            "total": total,
            "simulation_success": successful,
            "simulation_failed": failed_sim,
            "checked": len(checked),
            "check_pass": pass_count,
            "check_fail": fail_count,
            "check_pending": pending_count,
            "submitted": len(submitted),
        }


# ============================================================
# Report generation
# ============================================================

def generate_report(results: list, submitted: list, summary: dict, 
                   output_path: str = None) -> str:
    """Generate a markdown report."""
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines.append("# ACE 批量因子回测与提交检查报告")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**因子总数**: {summary['total']}")
    lines.append(f"**回测成功**: {summary['simulation_success']}")
    lines.append(f"**通过全部检查**: {summary['check_pass']} 个")
    lines.append(f"**正式提交成功**: {summary['submitted']} 个")
    lines.append("")
    
    # Summary table
    lines.append("## 汇总结果")
    lines.append("")
    lines.append("| 因子名称 | Alpha ID | Sharpe | Fitness | 自相关性 | 检查状态 | 生产相关性 | 正式提交 |")
    lines.append("|---------|----------|--------|---------|----------|----------|------------|----------|")
    
    for r in results:
        alpha_id = r.get("alpha_id", "N/A")
        factor_name = r.get("factor_name", "unknown")
        submit_check = r.get("submit_check", {})
        sharpe = submit_check.get("sharpe", "N/A")
        fitness = submit_check.get("fitness", "N/A")
        self_corr = submit_check.get("self_correlation", "N/A")
        status = submit_check.get("status", "N/A")
        prod_corr = r.get("prod_corr", {})
        prod_status = prod_corr.get("status", "N/A")
        prod_value = prod_corr.get("value")
        
        status_icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "PENDING": "⏳ PENDING", "ERROR": "⚠️ ERROR"}.get(status, status)
        prod_icon = {"PASS": "✅", "FAIL": "❌", "NONE": "—", "ERROR": "⚠️"}.get(prod_status, prod_status)
        if prod_value is not None:
            prod_display = f"{prod_icon} {prod_value:.4f}" if isinstance(prod_value, (int, float)) else f"{prod_icon} {prod_value}"
        else:
            prod_display = f"{prod_icon}"
        
        submit_icon = "✅" if any(s.get("alpha_id") == alpha_id for s in submitted) else "—"
        
        lines.append(f"| {factor_name} | {alpha_id} | {sharpe} | {fitness} | {self_corr} | {status_icon} | {prod_display} | {submit_icon} |")
    
    lines.append("")
    
    # Detailed check results
    lines.append("## 8项检查详细结果")
    lines.append("")
    
    for r in results:
        alpha_id = r.get("alpha_id", "N/A")
        factor_name = r.get("factor_name", "unknown")
        submit_check = r.get("submit_check", {})
        checks = submit_check.get("checks", {})
        
        if not checks:
            continue
        
        lines.append(f"### {factor_name} ({alpha_id})")
        lines.append("")
        lines.append("| 检查项 | 状态 | 数值 | 阈值 |")
        lines.append("|--------|------|------|------|")
        
        for check_name in SUBMISSION_CHECK_ITEMS:
            check_info = checks.get(check_name, {})
            status = check_info.get("status", "N/A")
            value = check_info.get("value", "-")
            limit = check_info.get("limit", "-")
            
            status_icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARNING": "⚠️ WARNING", "PENDING": "⏳ PENDING"}.get(status, status)
            
            value_str = f"{value:.4f}" if isinstance(value, (int, float)) else str(value)
            limit_str = f"{limit:.4f}" if isinstance(limit, (int, float)) else str(limit)
            
            lines.append(f"| {check_name} | {status_icon} | {value_str} | {limit_str} |")
        
        lines.append("")
    
    # Submission results
    lines.append("## 正式提交结果")
    lines.append("")
    
    if submitted:
        lines.append("以下因子已正式提交：")
        lines.append("")
        for s in submitted:
            lines.append(f"- {s['factor_name']} ({s['alpha_id']})")
        lines.append("")
    else:
        lines.append("本次检查中没有因子通过全部 8 项检查，未执行正式提交。")
        lines.append("")
    
    report_text = "\n".join(lines)
    
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"\n[ACE] 报告已保存到: {output_path}")
    
    return report_text


# ============================================================
# Main entry point
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(description="ACE Batch Factor Runner")
    parser.add_argument("expressions", nargs="*", help="Factor expressions (or use --file for batch)")
    parser.add_argument("--file", "-f", help="File with one expression per line")
    parser.add_argument("--names", "-n", help="Comma-separated factor names")
    parser.add_argument("--check-ids", help="Comma-separated existing alpha IDs to check (skip simulation)")
    parser.add_argument("--region", default="USA", help="Region (default: USA)")
    parser.add_argument("--universe", default="TOP3000", help="Universe (default: TOP3000)")
    parser.add_argument("--delay", type=int, default=1, help="Delay (default: 1)")
    parser.add_argument("--decay", type=int, default=0, help="Decay (default: 0)")
    parser.add_argument("--neutralization", default="INDUSTRY", help="Neutralization (default: INDUSTRY)")
    parser.add_argument("--truncation", type=float, default=0.08, help="Truncation (default: 0.08)")
    parser.add_argument("--pasteurization", default="ON", help="Pasteurization (default: ON)")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for multi-sim (default: 10)")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent batches (default: 3)")
    parser.add_argument("--auto-submit", action="store_true", help="Auto-submit passing factors")
    parser.add_argument("--prod-corr-threshold", type=float, default=0.7, help="Prod corr threshold (default: 0.7)")
    parser.add_argument("--db-path", default=DB_PATH, help=f"Database path (default: {DB_PATH})")
    parser.add_argument("--report", help="Output report path")
    parser.add_argument("--result-mode", default="display_only", choices=["display_only", "no_reply", "auto"])
    parser.add_argument("--email", help="WQB email")
    parser.add_argument("--password", help="WQB password")
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Set credentials
    if args.email:
        os.environ["BRAIN_CREDENTIAL_EMAIL"] = args.email
    if args.password:
        os.environ["BRAIN_CREDENTIAL_PASSWORD"] = args.password
    
    # Get factor names
    factor_names = None
    if args.names:
        factor_names = [n.strip() for n in args.names.split(",")]
    
    # Build settings
    settings = DEFAULT_SETTINGS.copy()
    settings["region"] = args.region
    settings["universe"] = args.universe
    settings["delay"] = args.delay
    settings["decay"] = args.decay
    settings["neutralization"] = args.neutralization
    settings["truncation"] = args.truncation
    settings["pasteurization"] = args.pasteurization
    
    # Create runner
    runner = ACEBatchRunner(
        db_path=args.db_path,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        auto_submit=args.auto_submit,
        prod_corr_threshold=args.prod_corr_threshold,
        settings=settings,
    )
    
    # Check mode: check existing alpha IDs
    if args.check_ids:
        alpha_ids = [aid.strip() for aid in args.check_ids.split(",") if aid.strip()]
        print(f"[ACE] 检查模式：{len(alpha_ids)} 个已有因子")
        
        runner.login()
        checked_results = runner.check_existing_alphas(alpha_ids, factor_names)
        submitted = runner.auto_submit_passing(checked_results)
        summary = runner.generate_summary(checked_results, submitted)
        
        result = {
            "results": checked_results,
            "submitted": submitted,
            "summary": summary,
        }
    else:
        # Get expressions
        expressions = []
        if args.file:
            with open(args.file, "r") as f:
                expressions = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        elif args.expressions:
            expressions = list(args.expressions)
        
        if not expressions:
            print("Error: No expressions provided. Use positional args, --file, or --check-ids.")
            return 1
        
        # Run full pipeline
        result = runner.run(expressions, factor_names)
    
    # Generate report
    report_path = args.report
    if not report_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(OUTPUT_DIR, f"ace_batch_report_{timestamp}.md")
    
    report = generate_report(
        result["results"],
        result["submitted"],
        result["summary"],
        output_path=report_path,
    )
    
    # Print summary
    print("\n" + "=" * 60)
    print("执行完成")
    print(f"  总数: {result['summary']['total']}")
    print(f"  回测成功: {result['summary']['simulation_success']}")
    print(f"  通过检查: {result['summary']['check_pass']}")
    print(f"  已提交: {result['summary']['submitted']}")
    print(f"  报告: {report_path}")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
