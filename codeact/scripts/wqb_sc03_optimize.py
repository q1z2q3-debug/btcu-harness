#!/usr/bin/env python3
"""
WQB SC03 Optimization — 12因子优化设计与回测脚本

基于首次回测结果（A组6/6 SC<0.3但Sharpe全负）的优化版本：
- 将ts_delta窗口从1日延长到5/10日，增强信号强度
- 引入ts_argmax/ts_argmin/ts_corr等低SC结构
- 保持SC<0.3为首要目标，同时追求Sharpe>0

回测设置：EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY,
          truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

用法：
  python wqb_sc03_optimize.py [--group A|B|all] [--delay 45] [--result-mode display_only]
"""

import asyncio
import json
import os
import sys
import time
import sqlite3
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

# ============================================================
# Path setup
# ============================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ACE_LIB_DIR = os.path.join(_SCRIPT_DIR, "ace_lib")
_OUTPUT_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "output"))
_DB_PATH = os.path.join(_OUTPUT_DIR, "wqb_state.db")

sys.path.insert(0, _ACE_LIB_DIR)

# Credentials
os.environ.setdefault("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
os.environ.setdefault("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")

import pandas as pd
import ace_lib
from codeact_sdk import CodeActSDK

# ============================================================
# Backtest settings (same as original)
# ============================================================
BT_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 0,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "maxTrade": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}

# ============================================================
# A组：6个扩展ts_delta因子（延长delta窗口至5/10日）
# 原版 ts_delta(ts_rank(X, 20), 1) 的SC极低（~0.1）但信号太弱
# 延长窗口后应保留低SC特性，同时增强信号强度
# ============================================================
A_FACTORS = [
    ("A1_close_rank_d5",
     "rank(ts_delta(ts_rank(close, 20), 5))",
     "5日收盘价排名变化 — 比1日版本信号更强"),
    ("A2_close_rank_d10",
     "rank(ts_delta(ts_rank(close, 20), 10))",
     "10日收盘价排名变化 — 捕捉中期趋势"),
    ("A3_volume_rank_d5",
     "rank(ts_delta(ts_rank(volume, 20), 5))",
     "5日成交量排名变化 — 量能变化信号"),
    ("A4_ma5_rank_d5",
     "rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 5))",
     "5日MA5排名变化 — 平滑后的趋势变化"),
    ("A5_mom5_rank_d5",
     "rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 5))",
     "5日动量排名变化 — 动量加速度"),
    ("A6_rank_acc_d10",
     "rank(ts_sum(ts_delta(ts_rank(close, 20), 1), 10))",
     "10日累计排名变化 — 累积方向信号"),
]

# ============================================================
# B组：6个替代低SC结构因子
# 使用完全不同的因子结构，利用SC天然低的特性
# ============================================================
B_FACTORS = [
    ("B7_argmax_pos",
     "rank(ts_argmax(close, 20))",
     "20日最高价位置 — 值越大越接近新高(0=今天,19=20天前)"),
    ("B8_argmin_pos",
     "rank(ts_argmin(close, 20))",
     "20日最低价位置 — 值越大越接近新低"),
    ("B9_argmax_delta",
     "rank(ts_delta(ts_argmax(close, 20), 5))",
     "5日argmax位置变化 — 最近高点位置的变化趋势"),
    ("B10_pv_corr_short",
     "rank(ts_corr(rank(close), rank(volume), 5))",
     "5日量价相关性 — 短期量价配合程度"),
    ("B11_corr_delta",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 5))",
     "5日量价相关性变化 — 量价关系趋势变化"),
    ("B12_range_delta",
     "rank(ts_delta(ts_max(high, 5) - ts_min(low, 5), 1))",
     "1日波动区间变化 — 波动率日变化"),
]

# Combine all factors
ALL_FACTORS = {
    "A": A_FACTORS,
    "B": B_FACTORS,
}

# Target thresholds
TARGET_SC = 0.3
TARGET_SHARPE = 1.6
TARGET_FITNESS = 2.5
TARGET_DRAWDOWN = 0.10


# ============================================================
# Database helpers
# ============================================================

def compute_expr_hash(expression: str, settings: dict) -> str:
    settings_normalized = json.dumps(settings, sort_keys=True)
    combined = f"{expression}|{settings_normalized}"
    return hashlib.md5(combined.encode()).hexdigest()


def ensure_db(db_path: str):
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


def is_already_simulated(db_path: str, expression: str, settings: dict,
                         factor_name: str) -> bool:
    """Check if this factor is already in the database with results."""
    expr_hash = compute_expr_hash(expression, settings)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT alpha_id, status FROM alphas WHERE expr_hash = ?",
        (expr_hash,)
    ).fetchone()
    conn.close()
    if row and row[0] and row[1] == "COMPLETED":
        print(f"  [{factor_name}] 已存在, alpha_id={row[0]}, 跳过")
        return True
    return False


def save_alpha_result(db_path: str, factor_name: str, expression: str,
                      alpha_type: str, alpha_id: str, settings: dict,
                      sharpe, fitness, annual_return, max_drawdown, turnover,
                      self_correlation, sc_result, is_stats: dict, checks: list):
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()

    expr_hash = compute_expr_hash(expression, settings)
    settings_json = json.dumps(settings, sort_keys=True)
    is_summary_json = json.dumps(is_stats) if is_stats else None
    checks_json = json.dumps(checks) if checks else None

    existing = conn.execute(
        "SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE alphas SET
                alpha_id = ?, status = 'COMPLETED',
                sharpe = ?, fitness = ?, annual_return = ?,
                max_drawdown = ?, turnover = ?,
                is_summary = ?, completed_at = ?
            WHERE expr_hash = ?
        """, (alpha_id, sharpe, fitness, annual_return, max_drawdown, turnover,
              is_summary_json, now, expr_hash))
    else:
        conn.execute("""
            INSERT INTO alphas
            (expr_hash, expression, factor_name, category, settings_json, alpha_id, status,
             sharpe, fitness, annual_return, max_drawdown, turnover, is_summary, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?, ?, ?)
        """, (expr_hash, expression, factor_name, alpha_type, settings_json, alpha_id,
              sharpe, fitness, annual_return, max_drawdown, turnover, is_summary_json, now))

    existing_check = conn.execute(
        "SELECT alpha_id FROM submit_checks WHERE alpha_id = ?", (alpha_id,)
    ).fetchone()

    passed = 1 if sc_result == "PASS" else 0

    if existing_check:
        conn.execute("""
            UPDATE submit_checks SET
                factor_name = ?, checked_at = ?, status = ?,
                self_correlation = ?, sharpe = ?, fitness = ?,
                turnover = ?, checks_json = ?, passed = ?
            WHERE alpha_id = ?
        """, (factor_name, now, sc_result, self_correlation, sharpe, fitness,
              turnover, checks_json, passed, alpha_id))
    else:
        conn.execute("""
            INSERT INTO submit_checks
            (alpha_id, factor_name, checked_at, status, self_correlation,
             sharpe, fitness, turnover, checks_json, passed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (alpha_id, factor_name, now, sc_result, self_correlation, sharpe,
              fitness, turnover, checks_json, passed))

    conn.commit()
    conn.close()


# ============================================================
# Metric extraction
# ============================================================

def extract_metrics(result: dict) -> dict:
    """Extract metrics from ACE simulation result."""
    alpha_id = result.get("alpha_id")
    if alpha_id is None:
        return {"alpha_id": None, "error": "simulation_failed"}

    is_stats = result.get("is_stats")
    is_tests = result.get("is_tests")

    sharpe = None
    fitness = None
    annual_return = None
    max_drawdown = None
    turnover = None

    if is_stats is not None and not is_stats.empty:
        row = is_stats.iloc[0]
        for col in row.index:
            val = row[col]
            if pd.notna(val):
                if col == "sharpe":
                    sharpe = float(val)
                elif col == "fitness":
                    fitness = float(val)
                elif col == "annualReturn":
                    annual_return = float(val)
                elif col == "maxDrawdown":
                    max_drawdown = float(val)
                elif col == "turnover":
                    turnover = float(val)

    self_correlation = None
    sc_result = "UNKNOWN"
    checks_list = []

    if is_tests is not None and not is_tests.empty:
        for _, row in is_tests.iterrows():
            name = str(row.get("name", ""))
            check_result = str(row.get("result", ""))
            value = float(row["value"]) if pd.notna(row.get("value")) else None
            limit = float(row["limit"]) if pd.notna(row.get("limit")) else None

            check = {"name": name, "result": check_result, "value": value, "limit": limit}
            checks_list.append(check)

            if name == "SELF_CORRELATION":
                self_correlation = value
                sc_result = check_result

    is_stats_dict = {}
    if is_stats is not None and not is_stats.empty:
        row = is_stats.iloc[0]
        for col in row.index:
            val = row[col]
            if pd.notna(val):
                try:
                    is_stats_dict[col] = float(val) if isinstance(val, (int, float)) else str(val)
                except (ValueError, TypeError):
                    is_stats_dict[col] = str(val)

    return {
        "alpha_id": alpha_id,
        "sharpe": sharpe,
        "fitness": fitness,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "self_correlation": self_correlation,
        "sc_result": sc_result,
        "checks": checks_list,
        "is_stats": is_stats_dict,
    }


def submit_batch(session, alpha_list, factor_names, alpha_type, expressions):
    """Submit a batch of factors, wait for completion, then fetch SC."""
    results = ace_lib.simulate_alpha_list(
        session, alpha_list,
        limit_of_concurrent_simulations=1,
        simulation_config=ace_lib.DEFAULT_CONFIG,
    )
    # Fetch SC for each successful factor
    for i, r in enumerate(results):
        aid = r.get("alpha_id")
        if aid:
            try:
                sc_df = ace_lib.get_self_corr(session, aid)
                if sc_df is not None and not sc_df.empty:
                    sc_value = float(sc_df["correlation"].max())
                    sc_result_str = "PASS" if sc_value < 0.7 else "FAIL"
                    sc_row = pd.DataFrame([{
                        "name": "SELF_CORRELATION",
                        "result": sc_result_str,
                        "value": sc_value,
                        "limit": 0.7,
                        "alpha_id": aid,
                    }])
                    if r.get("is_tests") is not None:
                        r["is_tests"] = pd.concat(
                            [r["is_tests"], sc_row], ignore_index=True
                        )
                    print(f"  [{factor_names[i]}] SC={sc_value:.4f}")
            except Exception as sc_e:
                print(f"  [{factor_names[i]}] SC获取失败: {sc_e}")
    return results


# ============================================================
# Report generation
# ============================================================

def generate_report(all_results: list, output_path: str, group_name: str) -> str:
    """Generate detailed markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total = len(all_results)
    successful = [r for r in all_results if r.get("alpha_id")]
    sc_pass = [r for r in successful if r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC]
    sharpe_pos = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0]
    sharpe_gt_16 = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE]
    fitness_gt_25 = [r for r in successful if r.get("fitness") is not None and r["fitness"] > TARGET_FITNESS]
    dd_lt_10 = [r for r in successful if r.get("max_drawdown") is not None and abs(r["max_drawdown"]) < TARGET_DRAWDOWN]
    candidates = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0.5]

    lines = []
    lines.append(f"# WQB SC03 优化回测 — 12因子优化设计与回测报告（{group_name}组）")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M")
    lines.append("")
    lines.append(f"**优化目标**: 保持SC<0.3为首要目标，同时追求Sharpe>0")
    lines.append("")
    lines.append("## 总体统计")
    lines.append("")
    lines.append("| 指标 | 数值 | 设计目标 | 达标 |")
    lines.append("|------|------|---------|------|")
    lines.append(f"| 因子总数 | {total} | — | — |")
    lines.append(f"| 回测成功 | {len(successful)}/{total} | {total}/{total} | {'✅' if len(successful)==total else '⚠️'} |")
    lines.append(f"| SC < {TARGET_SC} | {len(sc_pass)}/{total} | {total}/{total} | {'✅' if len(sc_pass)==total else '⚠️'} |")
    lines.append(f"| Sharpe > 0 | {len(sharpe_pos)}/{total} | 越多越好 | — |")
    lines.append(f"| Sharpe > {TARGET_SHARPE} | {len(sharpe_gt_16)}/{total} | — | — |")
    lines.append(f"| Sharpe > 0.5 候选 | {len(candidates)}/{total} | — | — |")
    lines.append(f"| Fitness > {TARGET_FITNESS} | {len(fitness_gt_25)}/{total} | — | — |")
    lines.append(f"| 回撤 < {TARGET_DRAWDOWN*100:.0f}% | {len(dd_lt_10)}/{total} | — | — |")
    lines.append("")

    # Results table
    lines.append("## 因子回测结果明细")
    lines.append("")
    lines.append("| 因子 | 设计思路 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 自相关(SC) | SC<0.3? | Sharpe>0? |")
    lines.append("|------|---------|----------|--------|---------|---------|---------|--------|-----------|---------|----------|")

    for r in all_results:
        name = r["factor_name"]
        design = r.get("design_desc", "")
        aid = r.get("alpha_id") or "FAILED"
        sharpe_s = f"{r['sharpe']:.4f}" if r.get("sharpe") is not None else "N/A"
        fitness_s = f"{r['fitness']:.4f}" if r.get("fitness") is not None else "N/A"
        ret_s = f"{r['annual_return']*100:.2f}%" if r.get("annual_return") is not None else "N/A"
        dd_s = f"{r['max_drawdown']*100:.2f}%" if r.get("max_drawdown") is not None else "N/A"
        to_s = f"{r['turnover']:.2f}" if r.get("turnover") is not None else "N/A"
        sc_s = f"{r['self_correlation']:.4f}" if r.get("self_correlation") is not None else "N/A"

        sc_ok = r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC
        sc_flag = "✅" if sc_ok else "❌" if r.get("self_correlation") is not None else "N/A"

        sp_ok = r.get("sharpe") is not None and r["sharpe"] > 0
        sp_flag = "✅" if sp_ok else "❌" if r.get("sharpe") is not None else "N/A"

        lines.append(f"| {name} | {design} | {aid} | {sharpe_s} | {fitness_s} | {ret_s} | {dd_s} | {to_s} | {sc_s} | {sc_flag} | {sp_flag} |")

    lines.append("")

    # SC vs Sharpe analysis
    lines.append("## SC vs Sharpe 分析")
    lines.append("")
    lines.append("| 因子 | SC | Sharpe | 象限 |")
    lines.append("|------|----|--------|------|")
    for r in all_results:
        sc_val = r.get("self_correlation")
        sp_val = r.get("sharpe")
        if sc_val is not None and sp_val is not None:
            if sc_val < 0.3 and sp_val > 0:
                quadrant = "🎯 SC<0.3 & Sharpe>0 (理想)"
            elif sc_val < 0.3 and sp_val <= 0:
                quadrant = "📊 SC<0.3但Sharpe≤0 (需改进信号)"
            elif sc_val >= 0.3 and sp_val > 0:
                quadrant = "⚠️ SC≥0.3但Sharpe>0 (需降SC)"
            else:
                quadrant = "❌ SC≥0.3且Sharpe≤0 (不达标)"
            lines.append(f"| {r['factor_name']} | {sc_val:.4f} | {sp_val:.4f} | {quadrant} |")
        else:
            lines.append(f"| {r['factor_name']} | N/A | N/A | 数据不足 |")
    lines.append("")

    # Candidate screening
    candidates_sorted = sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True)
    if candidates_sorted:
        lines.append("## 候选因子 (Sharpe > 0.5)")
        lines.append("")
        lines.append("| 排名 | 因子 | Sharpe | Fitness | SC | 回撤 | SC<0.3? |")
        lines.append("|------|------|--------|---------|-----|------|---------|")
        for rank, r in enumerate(candidates_sorted, 1):
            sc_ok = r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC
            sc_label = "✅" if sc_ok else "❌"
            lines.append(f"| {rank} | {r['factor_name']} | {r.get('sharpe', 0):.4f} | {r.get('fitness', 0):.4f} | {r.get('self_correlation', 0):.4f} | {r.get('max_drawdown', 0)*100:.2f}% | {sc_label} |")
        lines.append("")
    else:
        lines.append("## 候选因子 (Sharpe > 0.5)")
        lines.append("")
        lines.append("无符合条件的候选因子。")
        lines.append("")

    # Detailed checks
    lines.append("## 各因子详细检查结果")
    lines.append("")

    for r in all_results:
        name = r["factor_name"]
        aid = r.get("alpha_id")
        if not aid:
            continue

        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- **设计思路**: {r.get('design_desc', 'N/A')}")
        lines.append(f"- **表达式**: `{r.get('expression', 'N/A')}`")
        lines.append(f"- **Alpha ID**: {aid}")
        lines.append(f"- **Sharpe**: {r['sharpe']:.4f}" if r.get("sharpe") is not None else "- **Sharpe**: N/A")
        lines.append(f"- **Fitness**: {r['fitness']:.4f}" if r.get("fitness") is not None else "- **Fitness**: N/A")
        lines.append(f"- **SC**: {r['self_correlation']:.4f}" if r.get("self_correlation") is not None else "- **SC**: N/A")

        if r.get("checks"):
            lines.append("")
            lines.append("| 检查项 | 结果 | 数值 | 阈值 |")
            lines.append("|--------|------|------|------|")
            for ck in r["checks"]:
                cname = ck.get("name", "")
                cresult = ck.get("result", "")
                cvalue = ck.get("value")
                climit = ck.get("limit")
                cv = f"{cvalue:.4f}" if cvalue is not None else "-"
                cl = f"{climit:.4f}" if climit is not None else "-"
                lines.append(f"| {cname} | {cresult} | {cv} | {cl} |")
        lines.append("")

    # Design methodology
    lines.append("## 优化设计方法论")
    lines.append("")
    lines.append("### 首次回测发现的问题")
    lines.append("")
    lines.append("原版A组`rank(ts_delta(ts_rank(X, 20), 1))`结构：")
    lines.append("- ✅ SC极低（平均0.0987），全部<0.3")
    lines.append("- ❌ 所有Sharpe为负或接近0（最高0.06）")
    lines.append("- 原因：1日排名变化属于高频噪声，在月频调仓下信号衰减严重")
    lines.append("")
    lines.append("### 优化方向")
    lines.append("")
    lines.append("**A组：延长ts_delta窗口**")
    lines.append("")
    lines.append("| 编号 | 公式 | 设计思路 |")
    lines.append("|------|------|---------|")
    for name, expr, desc in A_FACTORS:
        lines.append(f"| {name} | `{expr}` | {desc} |")
    lines.append("")
    lines.append("**B组：替代低SC结构**")
    lines.append("")
    lines.append("| 编号 | 公式 | 设计思路 |")
    lines.append("|------|------|---------|")
    for name, expr, desc in B_FACTORS:
        lines.append(f"| {name} | `{expr}` | {desc} |")
    lines.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return "\n".join(lines)


# ============================================================
# Main pipeline
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description="WQB SC03 Optimization - 12-factor optimized backtest")
    parser.add_argument("--result-mode", default="display_only",
                        choices=["display_only", "notify", "no_reply", "auto"])
    parser.add_argument("--db-path", default=_DB_PATH)
    parser.add_argument("--report", default=os.path.join(_OUTPUT_DIR, "wqb_sc03_optimize.md"))
    parser.add_argument("--group", default="all", choices=["all", "A", "B"],
                        help="Run only A or B group (default: all)")
    parser.add_argument("--delay", type=int, default=45,
                        help="Delay in seconds between submissions (default: 45)")
    args = parser.parse_args()

    result_mode = args.result_mode
    if result_mode == "auto":
        result_mode = "display_only"

    sdk = CodeActSDK()

    try:
        print(f"[WQB] 开始SC03优化回测...")
        print(f"[WQB] 回测设置: {BT_SETTINGS}")

        ensure_db(args.db_path)
        print(f"[WQB] 数据库已就绪: {args.db_path}")

        # Login
        print("[WQB] 登录WQB平台...")
        s = ace_lib.start_session()
        timeout = ace_lib.check_session_timeout(s)
        print(f"[WQB] 登录成功，会话有效期: {timeout/3600:.1f} 小时")

        all_results = []

        # ========================================
        # Process a group of factors
        # ========================================
        def process_group(factors, group_name):
            nonlocal all_results
            print(f"\n{'=' * 60}")
            print(f"[WQB] {group_name}组: {len(factors)}个因子")
            print(f"{'=' * 60}")

            alpha_list = []
            names = []
            exprs = []
            descs = []

            for name, expr, desc in factors:
                # Check if already simulated
                if is_already_simulated(args.db_path, expr, BT_SETTINGS, name):
                    # Load existing result from DB
                    conn = sqlite3.connect(args.db_path)
                    row = conn.execute(
                        "SELECT alpha_id, sharpe, fitness, annual_return, max_drawdown, turnover, is_summary FROM alphas WHERE expr_hash = ?",
                        (compute_expr_hash(expr, BT_SETTINGS),)
                    ).fetchone()
                    conn.close()
                    if row and row[0]:
                        metrics = {
                            "alpha_id": row[0],
                            "sharpe": row[1],
                            "fitness": row[2],
                            "annual_return": row[3],
                            "max_drawdown": row[4],
                            "turnover": row[5],
                            "self_correlation": None,
                            "sc_result": "UNKNOWN",
                            "checks": [],
                            "is_stats": json.loads(row[6]) if row[6] else {},
                            "factor_name": name,
                            "alpha_type": group_name,
                            "expression": expr,
                            "design_desc": desc,
                        }
                        # Try to load SC from self_corr table
                        try:
                            sc_row = conn.execute(
                                "SELECT correlation FROM self_corr WHERE alpha_id = ? ORDER BY fetched_at DESC LIMIT 1",
                                (row[0],)
                            ).fetchone()
                            if sc_row:
                                metrics["self_correlation"] = sc_row[0]
                                metrics["sc_result"] = "PASS" if sc_row[0] < 0.7 else "FAIL"
                        except:
                            pass
                        all_results.append(metrics)
                        return

                sim_data = ace_lib.generate_alpha(
                    regular=expr,
                    alpha_type="REGULAR",
                    region=BT_SETTINGS["region"],
                    universe=BT_SETTINGS["universe"],
                    delay=BT_SETTINGS["delay"],
                    decay=BT_SETTINGS["decay"],
                    neutralization=BT_SETTINGS["neutralization"],
                    truncation=BT_SETTINGS["truncation"],
                    pasteurization=BT_SETTINGS["pasteurization"],
                    test_period=BT_SETTINGS["testPeriod"],
                )
                alpha_list.append(sim_data)
                names.append(name)
                exprs.append(expr)
                descs.append(desc)
                print(f"  [{name}] {expr}")

            if not alpha_list:
                print(f"  [{group_name}组] 所有因子已存在，无需提交")
                return

            print(f"\n[WQB] 提交{group_name}组回测 (simulate_alpha_list, 1并发)...")
            batch_results = submit_batch(s, alpha_list, names, group_name, exprs)

            for i, (name, expr, desc) in enumerate(factors):
                # Find the corresponding result
                if i < len(batch_results):
                    r = batch_results[i]
                else:
                    r = {"alpha_id": None, "simulate_data": alpha_list[i] if i < len(alpha_list) else None}

                metrics = extract_metrics(r)
                metrics["factor_name"] = name
                metrics["alpha_type"] = group_name
                metrics["expression"] = expr
                metrics["design_desc"] = desc

                if metrics.get("alpha_id"):
                    save_alpha_result(
                        args.db_path, name, expr, group_name, metrics["alpha_id"],
                        BT_SETTINGS, metrics.get("sharpe"), metrics.get("fitness"),
                        metrics.get("annual_return"), metrics.get("max_drawdown"),
                        metrics.get("turnover"), metrics.get("self_correlation"),
                        metrics.get("sc_result", "UNKNOWN"), metrics.get("is_stats", {}), metrics.get("checks", [])
                    )

                all_results.append(metrics)
                status = "✅" if metrics["alpha_id"] else "❌"
                sc_str = f"SC={metrics['self_correlation']:.4f}" if metrics.get("self_correlation") is not None else "SC=N/A"
                sp_str = f"Sharpe={metrics['sharpe']:.4f}" if metrics.get("sharpe") is not None else "Sharpe=N/A"
                print(f"  [{name}] {status} | {sp_str} | {sc_str}")

        # ========================================
        # Process groups
        # ========================================
        if args.group in ("all", "A"):
            process_group(A_FACTORS, "A")
            if args.group == "all":
                print(f"\n[WQB] A组完成，等待120秒后开始B组...")
                time.sleep(120)

        if args.group in ("all", "B"):
            process_group(B_FACTORS, "B")

        # ========================================
        # Generate report
        # ========================================
        if all_results:
            group_name = args.group.upper() if args.group != "all" else "ALL"
            print(f"\n[WQB] 生成报告...")
            report_path = args.report
            report_text = generate_report(all_results, report_path, group_name)
            abs_report_path = os.path.abspath(report_path)
            print(f"[WQB] 报告已保存到: {abs_report_path}")

            # Summary
            successful = [r for r in all_results if r.get("alpha_id")]
            sc_pass = [r for r in successful if r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC]
            sharpe_pos = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0]
            candidates = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0.5]

            print(f"\n{'=' * 60}")
            print(f"[WQB] 执行完成")
            print(f"  成功: {len(successful)}/{len(all_results)}")
            print(f"  SC<{TARGET_SC}: {len(sc_pass)}/{len(all_results)}")
            print(f"  Sharpe>0: {len(sharpe_pos)}/{len(all_results)}")
            print(f"  Sharpe>0.5候选: {len(candidates)}")
            print(f"{'=' * 60}")

            # Build message
            msg_lines = [
                f"WQB SC03优化回测完成 — {group_name}组结果",
                "",
                f"**回测设置**: EQUITY/USA/TOP3000, SUBINDUSTRY, testPeriod=P1Y6M",
                f"**成功回测**: {len(successful)}/{len(all_results)}",
                f"**SC<{TARGET_SC}**: {len(sc_pass)}/{len(all_results)}",
                f"**Sharpe>0**: {len(sharpe_pos)}/{len(all_results)}",
                f"**Sharpe>0.5候选**: {len(candidates)}",
                "",
            ]

            if sc_pass:
                msg_lines.append("**SC<0.3因子:**")
                for r in sorted(sc_pass, key=lambda x: x.get("sharpe") or 0, reverse=True):
                    sp_str = f"Sharpe={r.get('sharpe', 'N/A'):.4f}" if r.get('sharpe') is not None else "Sharpe=N/A"
                    msg_lines.append(f"  - {r['factor_name']}: {sp_str}, SC={r.get('self_correlation', 'N/A'):.4f}")

            if sharpe_pos:
                msg_lines.append("")
                msg_lines.append("**Sharpe>0因子:**")
                for r in sorted(sharpe_pos, key=lambda x: x.get("sharpe") or 0, reverse=True):
                    sc_str = f"SC={r.get('self_correlation', 'N/A'):.4f}" if r.get('self_correlation') is not None else "SC=N/A"
                    msg_lines.append(f"  - {r['factor_name']}: Sharpe={r.get('sharpe', 'N/A'):.4f}, {sc_str}")

            msg_lines.append("")
            msg_lines.append(f"完整报告: [wqb_sc03_optimize.md](computer://{abs_report_path})")

            message = "\n".join(msg_lines)

            await sdk.submit_result(
                result_mode=result_mode,
                status="success",
                message=message,
                data={
                    "report_path": report_path,
                    "total": len(all_results),
                    "successful": len(successful),
                    "sc_pass": len(sc_pass),
                    "sharpe_pos": len(sharpe_pos),
                    "candidates": len(candidates),
                    "all_results": [
                        {
                            "factor_name": r["factor_name"],
                            "alpha_type": r["alpha_type"],
                            "alpha_id": r.get("alpha_id"),
                            "sharpe": r.get("sharpe"),
                            "fitness": r.get("fitness"),
                            "self_correlation": r.get("self_correlation"),
                            "max_drawdown": r.get("max_drawdown"),
                            "annual_return": r.get("annual_return"),
                            "design_desc": r.get("design_desc", ""),
                        }
                        for r in all_results
                    ],
                },
            )
        else:
            await sdk.submit_result(
                result_mode="display_only",
                status="success",
                message="无因子需要回测（所有因子已在数据库中）。",
                data={"skipped": True},
            )

    except Exception as e:
        print(f"[WQB] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"WQB SC03优化回测执行失败: {e}",
            data={"error_type": type(e).__name__, "error": str(e)},
        )


if __name__ == "__main__":
    asyncio.run(main())