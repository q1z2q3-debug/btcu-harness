#!/usr/bin/env python3
"""
WQB SC03 Breakthrough — 12因子设计与回测筛选脚本

设计目标：SC<0.3为主，追求Sharpe>1.6、Fitness>2.5、回撤<10%
两组因子：
  A组 (6个REGULAR): rank(ts_delta(ts_rank(X, N), 1)) 排名变化类
  B组 (6个SUPER): selection+combo 结构

回测设置：EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY,
          truncation=0.08, pasteurization=ON, testPeriod=P1Y6M

用法：
  python wqb_sc03_breakthrough.py [--result-mode display_only] [--db-path ...] [--report ...]
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
# Path setup — must be before ACE imports
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
# Constants
# ============================================================

# 回测设置（任务要求）
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

# A组：6个REGULAR ts_delta排名变化因子
A_FACTORS = [
    ("A1_close_rank_delta", "rank(ts_delta(ts_rank(close, 20), 1))"),
    ("A2_volume_rank_delta", "rank(ts_delta(ts_rank(volume, 20), 1))"),
    ("A3_ma5_rank_delta", "rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 1))"),
    ("A4_high_rank_delta", "rank(ts_delta(ts_rank(high, 20), 1))"),
    ("A5_low_rank_delta", "rank(ts_delta(ts_rank(low, 20), 1))"),
    ("A6_mom5_rank_delta", "rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 1))"),
]

# B组：6个SUPER alpha，因账号无SUPER权限，转为REGULAR表达式
# 转换方式：combo * indicator(selection)，其中indicator(selection) = rank(X) > threshold
B_FACTORS = [
    ("B7_super_top20_close_rank",
     "rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_rank(close, 20)) > 0.8)"),
    ("B8_super_top20_vol_high",
     "rank(ts_delta(ts_rank(close, 5), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.8)"),
    ("B9_super_top20_vol_close",
     "rank(ts_delta(ts_rank(close, 20), 1)) * (rank(volume) > 0.8)"),
    ("B10_super_top20_price_vol",
     "rank(ts_delta(ts_rank(volume, 20), 1)) * (rank(ts_mean(close, 5)) > 0.8)"),
    ("B11_super_top30_vol_high",
     "rank(ts_delta(ts_rank(high, 20), 1)) * (rank(ts_mean(abs(returns), 20)) > 0.7)"),
    ("B12_super_top30_mom_close",
     "rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_delta(close, 5)) > 0.7)"),
]

# 目标阈值
TARGET_SC = 0.3
TARGET_SHARPE = 1.6
TARGET_FITNESS = 2.5
TARGET_DRAWDOWN = 0.10  # 10%


# ============================================================
# Database helpers
# ============================================================

def compute_expr_hash(expression: str, settings: dict) -> str:
    """Compute unique hash for expression+settings combination."""
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


def save_alpha_result(db_path: str, factor_name: str, expression: str,
                      alpha_type: str, alpha_id: str, settings: dict,
                      sharpe, fitness, annual_return, max_drawdown, turnover,
                      self_correlation, sc_result, is_stats: dict, checks: list):
    """Save alpha result to database."""
    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()

    expr_hash = compute_expr_hash(expression, settings)
    settings_json = json.dumps(settings, sort_keys=True)
    is_summary_json = json.dumps(is_stats) if is_stats else None
    checks_json = json.dumps(checks) if checks else None

    # Upsert alphas table
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

    # Upsert submit_checks table
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
# Metric extraction from ACE simulation results
# ============================================================

def extract_metrics(result: dict) -> dict:
    """Extract Sharpe, Fitness, SC, drawdown, etc from ACE simulation result."""
    alpha_id = result.get("alpha_id")
    if alpha_id is None:
        return {"alpha_id": None, "error": "simulation_failed"}

    is_stats = result.get("is_stats")
    is_tests = result.get("is_tests")

    # Extract from is_stats DataFrame
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

    # Extract SC from is_tests checks
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

    # Build is_stats dict
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


# ============================================================
# Report generation
# ============================================================

def generate_report(all_results: list, output_path: str) -> str:
    """Generate detailed markdown report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Overall stats
    total = len(all_results)
    successful = [r for r in all_results if r["alpha_id"]]
    sc_pass = [r for r in successful if r["self_correlation"] is not None and r["self_correlation"] < TARGET_SC]
    sharpe_gt_16 = [r for r in successful if r["sharpe"] is not None and r["sharpe"] > TARGET_SHARPE]
    fitness_gt_25 = [r for r in successful if r["fitness"] is not None and r["fitness"] > TARGET_FITNESS]
    dd_lt_10 = [r for r in successful if r["max_drawdown"] is not None and abs(r["max_drawdown"]) < TARGET_DRAWDOWN]
    candidates = [r for r in successful if r["sharpe"] is not None and r["sharpe"] > 1.0]

    # All targets met
    all_targets = [r for r in successful if (
        r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE and
        r.get("fitness") is not None and r["fitness"] > TARGET_FITNESS and
        r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC and
        r.get("max_drawdown") is not None and abs(r["max_drawdown"]) < TARGET_DRAWDOWN
    )]

    lines = []
    lines.append("# WQB SC03 突破回测 — 12因子设计与回测报告")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append(f"**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M")
    lines.append("")
    lines.append("## 总体统计")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 因子总数 | {total} |")
    lines.append(f"| 回测成功 | {len(successful)}/{total} |")
    lines.append(f"| SC < {TARGET_SC} (设计目标) | {len(sc_pass)}/{total} |")
    lines.append(f"| Sharpe > 1.0 | {len(candidates)}/{total} |")
    lines.append(f"| Sharpe > {TARGET_SHARPE} | {len(sharpe_gt_16)}/{total} |")
    lines.append(f"| Fitness > {TARGET_FITNESS} | {len(fitness_gt_25)}/{total} |")
    lines.append(f"| 回撤 < {TARGET_DRAWDOWN*100:.0f}% | {len(dd_lt_10)}/{total} |")
    lines.append(f"| 全部达标 | {len(all_targets)}/{total} |")
    lines.append("")

    # Results table
    lines.append("## 因子回测结果明细")
    lines.append("")
    lines.append("| 因子 | 类型 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | 自相关(SC) | SC判定 | 达标项 |")
    lines.append("|------|------|----------|--------|---------|---------|---------|--------|-----------|--------|--------|")

    for r in all_results:
        name = r["factor_name"]
        atype = r["alpha_type"]
        aid = r.get("alpha_id") or "FAILED"
        sharpe_s = f"{r['sharpe']:.4f}" if r.get("sharpe") is not None else "N/A"
        fitness_s = f"{r['fitness']:.4f}" if r.get("fitness") is not None else "N/A"
        ret_s = f"{r['annual_return']*100:.2f}%" if r.get("annual_return") is not None else "N/A"
        dd_s = f"{r['max_drawdown']*100:.2f}%" if r.get("max_drawdown") is not None else "N/A"
        to_s = f"{r['turnover']:.2f}" if r.get("turnover") is not None else "N/A"
        sc_s = f"{r['self_correlation']:.4f}" if r.get("self_correlation") is not None else "N/A"

        sc_ok = r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC
        sc_flag = "✅ <0.3" if sc_ok else "❌ ≥0.3" if r.get("self_correlation") is not None else "N/A"

        targets = []
        if r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE:
            targets.append("S")
        if r.get("fitness") is not None and r["fitness"] > TARGET_FITNESS:
            targets.append("F")
        if sc_ok:
            targets.append("SC")
        if r.get("max_drawdown") is not None and abs(r["max_drawdown"]) < TARGET_DRAWDOWN:
            targets.append("DD")

        target_str = "/".join(targets) if targets else "—"

        lines.append(f"| {name} | {atype} | {aid} | {sharpe_s} | {fitness_s} | {ret_s} | {dd_s} | {to_s} | {sc_s} | {sc_flag} | {target_str} |")

    lines.append("")

    # Candidate screening
    lines.append("## 候选因子筛选 (Sharpe > 1.0)")
    lines.append("")

    if candidates:
        candidates_sorted = sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True)
        lines.append("| 排名 | 因子 | Sharpe | Fitness | SC | 回撤 | 达标数 | 设计目标判断 |")
        lines.append("|------|------|--------|---------|-----|------|--------|-------------|")
        for rank, r in enumerate(candidates_sorted, 1):
            sc_ok = r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC
            sp_ok = r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE
            ft_ok = r.get("fitness") is not None and r["fitness"] > TARGET_FITNESS
            dd_ok = r.get("max_drawdown") is not None and abs(r["max_drawdown"]) < TARGET_DRAWDOWN
            score = sum([sc_ok, sp_ok, ft_ok, dd_ok])

            sc_label = "✅" if sc_ok else "❌"
            sp_label = "✅" if sp_ok else "❌"
            ft_label = "✅" if ft_ok else "❌"
            dd_label = "✅" if dd_ok else "❌"

            lines.append(f"| {rank} | {r['factor_name']} | {r.get('sharpe', 0):.4f} {sp_label} | {r.get('fitness', 0):.4f} {ft_label} | {r.get('self_correlation', 0):.4f} {sc_label} | {r.get('max_drawdown', 0)*100:.2f}% {dd_label} | {score}/4 | {'🎯 全部达标' if score == 4 else '部分达标'} |")
        lines.append("")
    else:
        lines.append("无符合条件的候选因子 (Sharpe > 1.0)。")
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
    lines.append("## 设计方法论")
    lines.append("")
    lines.append("### A组：ts_delta排名变化因子 (REGULAR)")
    lines.append("")
    lines.append("核心逻辑：`rank(ts_delta(ts_rank(X, N), 1))` — 某指标排名的1日变化量")
    lines.append("")
    lines.append("设计目标：利用排名变化（一阶差分）天然的低自相关特性，使SC < 0.3。")
    lines.append("")
    lines.append("| 编号 | 公式 | 设计思路 |")
    lines.append("|------|------|---------|")
    lines.append("| A1 | rank(ts_delta(ts_rank(close, 20), 1)) | 收盘价排名的日变化 |")
    lines.append("| A2 | rank(ts_delta(ts_rank(volume, 20), 1)) | 成交量排名的日变化 |")
    lines.append("| A3 | rank(ts_delta(ts_rank(ts_mean(close, 5), 20), 1)) | 5日均线排名的日变化 |")
    lines.append("| A4 | rank(ts_delta(ts_rank(high, 20), 1)) | 最高价排名的日变化 |")
    lines.append("| A5 | rank(ts_delta(ts_rank(low, 20), 1)) | 最低价排名的日变化 |")
    lines.append("| A6 | rank(ts_delta(ts_rank(ts_delta(close, 5), 20), 1)) | 5日动量排名的日变化 |")
    lines.append("")
    lines.append("### B组：SUPER Alpha (因账号限制转为REGULAR表达式)")
    lines.append("")
    lines.append("核心逻辑：原SUPER结构(selection+combo)因账号无SUPER权限，转为REGULAR表达式：`combo * indicator(selection)`")
    lines.append("")
    lines.append("| 编号 | REGULAR表达式 | 设计思路 |")
    lines.append("|------|-------------|---------|")
    lines.append("| B7 | rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_rank(close, 20)) > 0.8) | 前20%排名股中按排名变化排序 |")
    lines.append("| B8 | rank(ts_delta(ts_rank(close, 5), 1)) * (rank(ts_stddev(returns, 20)) > 0.8) | 高波动股中按排名变化排序 |")
    lines.append("| B9 | rank(ts_delta(ts_rank(close, 20), 1)) * (rank(volume) > 0.8) | 高成交股中按排名变化排序 |")
    lines.append("| B10 | rank(ts_delta(ts_rank(volume, 20), 1)) * (rank(ts_mean(close, 5)) > 0.8) | 高价股中按成交量排名变化排序 |")
    lines.append("| B11 | rank(ts_delta(ts_rank(high, 20), 1)) * (rank(ts_stddev(returns, 20)) > 0.7) | 高波动股中按最高价排名变化 |")
    lines.append("| B12 | rank(ts_delta(ts_rank(close, 20), 1)) * (rank(ts_delta(close, 5)) > 0.7) | 动量股中按排名变化排序 |")
    lines.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return "\n".join(lines)


# ============================================================
# Main pipeline
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description="WQB SC03 Breakthrough - 12-factor backtest")
    parser.add_argument("--result-mode", default="display_only",
                        choices=["display_only", "notify", "no_reply", "auto"])
    parser.add_argument("--db-path", default=_DB_PATH)
    parser.add_argument("--report", default=os.path.join(_OUTPUT_DIR, "wqb_sc03_breakthrough.md"))
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
        print(f"[WQB] 开始12因子SC03突破回测...")
        print(f"[WQB] 回测设置: {BT_SETTINGS}")

        # Ensure DB exists
        ensure_db(args.db_path)
        print(f"[WQB] 数据库已就绪: {args.db_path}")

        # Login to WQB
        print("[WQB] 登录WQB平台...")
        s = ace_lib.start_session()
        timeout = ace_lib.check_session_timeout(s)
        print(f"[WQB] 登录成功，会话有效期: {timeout/3600:.1f} 小时")

        all_results = []
        SUBMIT_INTERVAL = args.delay

        # ========================================
        # Helper: submit batch and fetch SC
        # ========================================
        def submit_batch(session, alpha_list, factor_names, alpha_type, expressions):
            """Submit a batch of factors, wait for completion, then fetch SC."""
            results = ace_lib.simulate_alpha_list(
                session, alpha_list,
                limit_of_concurrent_simulations=1,
                simulation_config=ace_lib.DEFAULT_CONFIG,
            )
            # After batch, fetch SC for each success
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

        # ========================================
        # A Group: 6 REGULAR factors
        # ========================================
        if args.group in ("all", "A"):
            print("\n" + "=" * 60)
            print("[WQB] A组: 6个REGULAR因子 (ts_delta排名变化)")
            print("=" * 60)

            a_alpha_list = []
            a_names = []
            for name, expr in A_FACTORS:
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
                a_alpha_list.append(sim_data)
                a_names.append(name)
                print(f"  [{name}] {expr}")

            print(f"\n[WQB] 提交A组回测 (simulate_alpha_list, 1并发)...")
            a_results = submit_batch(s, a_alpha_list, a_names, "REGULAR",
                                     [e for _, e in A_FACTORS])

            for i, (name, expr) in enumerate(A_FACTORS):
                r = a_results[i] if i < len(a_results) else {"alpha_id": None, "simulate_data": a_alpha_list[i]}
                metrics = extract_metrics(r)
                metrics["factor_name"] = name
                metrics["alpha_type"] = "REGULAR"
                metrics["expression"] = expr

                if metrics.get("alpha_id"):
                    save_alpha_result(
                        args.db_path, name, expr, "REGULAR", metrics["alpha_id"],
                        BT_SETTINGS, metrics.get("sharpe"), metrics.get("fitness"),
                        metrics.get("annual_return"), metrics.get("max_drawdown"),
                        metrics.get("turnover"), metrics.get("self_correlation"),
                        metrics.get("sc_result", "UNKNOWN"), metrics.get("is_stats", {}), metrics.get("checks", [])
                    )

                all_results.append(metrics)
                status = "✅" if metrics["alpha_id"] else "❌"
                print(f"  [{name}] {status} | Sharpe={metrics.get('sharpe')} | Fitness={metrics.get('fitness')} | SC={metrics.get('self_correlation')}")

        # ========================================
        # B Group: 6 REGULAR (原SUPER结构)
        # ========================================
        if args.group in ("all", "B"):
            # If running both groups, wait between groups
            if args.group == "all":
                print(f"\n[WQB] A组完成，等待120秒后开始B组（防429限流窗口重置）...")
                time.sleep(120)

            print("\n" + "=" * 60)
            print("[WQB] B组: 6个因子 (原SUPER结构转为REGULAR表达式)")
            print("=" * 60)

            b_alpha_list = []
            b_names = []
            for name, expr in B_FACTORS:
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
                b_alpha_list.append(sim_data)
                b_names.append(name)
                print(f"  [{name}] {expr}")

            print(f"\n[WQB] 提交B组回测 (simulate_alpha_list, 1并发)...")
            b_results = submit_batch(s, b_alpha_list, b_names, "REGULAR(原SUPER)",
                                     [e for _, e in B_FACTORS])

            for i, (name, expr) in enumerate(B_FACTORS):
                r = b_results[i] if i < len(b_results) else {"alpha_id": None, "simulate_data": b_alpha_list[i]}
                metrics = extract_metrics(r)
                metrics["factor_name"] = name
                metrics["alpha_type"] = "REGULAR(原SUPER)"
                metrics["expression"] = expr

                if metrics.get("alpha_id"):
                    save_alpha_result(
                        args.db_path, name, expr, "REGULAR(SUPER)", metrics["alpha_id"],
                        BT_SETTINGS, metrics.get("sharpe"), metrics.get("fitness"),
                        metrics.get("annual_return"), metrics.get("max_drawdown"),
                        metrics.get("turnover"), metrics.get("self_correlation"),
                        metrics.get("sc_result", "UNKNOWN"), metrics.get("is_stats", {}), metrics.get("checks", [])
                    )

                all_results.append(metrics)
                status = "✅" if metrics["alpha_id"] else "❌"
                print(f"  [{name}] {status} | Sharpe={metrics.get('sharpe')} | Fitness={metrics.get('fitness')} | SC={metrics.get('self_correlation')}")

        # ========================================
        # Generate report
        # ========================================
        print(f"\n[WQB] 生成报告...")
        report_path = args.report
        report_text = generate_report(all_results, report_path)
        abs_report_path = os.path.abspath(report_path)
        print(f"[WQB] 报告已保存到: {abs_report_path}")

        # ========================================
        # Summary and submit
        # ========================================
        successful = [r for r in all_results if r.get("alpha_id")]
        sc_pass = [r for r in successful if r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC]
        sharpe_gt_16 = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE]
        candidates = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 1.0]

        print("\n" + "=" * 60)
        print(f"[WQB] 执行完成")
        print(f"  成功: {len(successful)}/12")
        print(f"  SC<{TARGET_SC}: {len(sc_pass)}")
        print(f"  Sharpe>{TARGET_SHARPE}: {len(sharpe_gt_16)}")
        print(f"  Sharpe>1.0候选: {len(candidates)}")
        print("=" * 60)

        # Build message
        msg_lines = [
            f"WQB SC03突破回测完成 — 12因子回测与筛选结果",
            "",
            f"**回测设置**: EQUITY/USA/TOP3000, SUBINDUSTRY, testPeriod=P1Y6M",
            f"**成功回测**: {len(successful)}/12",
            f"**SC<{TARGET_SC}**: {len(sc_pass)}/12",
            f"**Sharpe>{TARGET_SHARPE}**: {len(sharpe_gt_16)}/12",
            f"**Sharpe>1.0候选**: {len(candidates)}/12",
            "",
        ]

        if candidates:
            msg_lines.append("**候选因子 (Sharpe>1.0, 按Sharpe排序):**")
            for rank, r in enumerate(sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True), 1):
                sc_ok = "✅" if (r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC) else "❌"
                sp_ok = "✅" if (r.get("sharpe") is not None and r["sharpe"] > TARGET_SHARPE) else "❌"
                msg_lines.append(f"  {rank}. {r['factor_name']}: Sharpe={r.get('sharpe', 'N/A')}{sp_ok}, Fitness={r.get('fitness', 'N/A')}, SC={r.get('self_correlation', 'N/A')}{sc_ok}")

        msg_lines.append("")
        msg_lines.append(f"完整报告: [wqb_sc03_breakthrough.md](computer://{abs_report_path})")

        message = "\n".join(msg_lines)

        await sdk.submit_result(
            result_mode=result_mode,
            status="success",
            message=message,
            data={
                "report_path": report_path,
                "total": 12,
                "successful": len(successful),
                "sc_pass": len(sc_pass),
                "sharpe_gt_1_6": len(sharpe_gt_16),
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
                    }
                    for r in all_results
                ],
            },
        )

    except Exception as e:
        print(f"[WQB] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        await sdk.submit_result(
            result_mode="notify",
            status="error",
            message=f"WQB SC03突破回测执行失败: {e}",
            data={"error_type": type(e).__name__, "error": str(e)},
        )


if __name__ == "__main__":
    asyncio.run(main())