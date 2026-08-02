#!/usr/bin/env python3
"""
WQB SC03 Optimization v2 — 基于A3/B11成功因子的参数扫描

第一轮发现：
  A3_volume_rank_d5:  rank(ts_delta(ts_rank(volume, 20), 5))  Sharpe=0.25, SC=0.1629
  B11_corr_delta:     rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 5))  Sharpe=0.05, SC=0.0889

本轮：对A3进行参数扫描（delta窗口/rank窗口），对B11进行参数扫描（corr窗口/delta窗口）
并探索新的低SC结构组合

回测设置：EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY,
          truncation=0.08, pasteurization=ON, testPeriod=P1Y6M
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

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ACE_LIB_DIR = os.path.join(_SCRIPT_DIR, "ace_lib")
_OUTPUT_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "output"))
_DB_PATH = os.path.join(_OUTPUT_DIR, "wqb_state.db")
sys.path.insert(0, _ACE_LIB_DIR)

os.environ.setdefault("BRAIN_CREDENTIAL_EMAIL", "q1z2q3@126.com")
os.environ.setdefault("BRAIN_CREDENTIAL_PASSWORD", "W2025zq0118")

import pandas as pd
import ace_lib
from codeact_sdk import CodeActSDK

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
# A组：A3_volume_rank_d5参数扫描
# ============================================================
A_FACTORS = [
    ("A3v_vol_rank_d3",
     "rank(ts_delta(ts_rank(volume, 20), 3))",
     "3日volume rank变化 — A3的短窗口变体"),
    ("A3v_vol_rank_d7",
     "rank(ts_delta(ts_rank(volume, 20), 7))",
     "7日volume rank变化 — A3的中窗口变体"),
    ("A3v_vol_rank_d10",
     "rank(ts_delta(ts_rank(volume, 20), 10))",
     "10日volume rank变化 — A3的长窗口变体"),
    ("A3v_vol_rank40_d5",
     "rank(ts_delta(ts_rank(volume, 40), 5))",
     "5日40日volume rank变化 — 更长rank窗口"),
    ("A3v_vol_rank60_d5",
     "rank(ts_delta(ts_rank(volume, 60), 5))",
     "5日60日volume rank变化 — 最长rank窗口"),
    ("A3v_vol_rank20_d15",
     "rank(ts_delta(ts_rank(volume, 20), 15))",
     "15日volume rank变化 — A3的最长delta窗口"),
]

# ============================================================
# B组：B11_corr_delta参数扫描 + 新低SC结构
# ============================================================
B_FACTORS = [
    ("B11v_corr5_d5",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 5), 5))",
     "5日量价corr的5日变化 — 短corr窗口"),
    ("B11v_corr15_d5",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 15), 5))",
     "15日量价corr的5日变化 — 中corr窗口"),
    ("B11v_corr20_d5",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 20), 5))",
     "20日量价corr的5日变化 — 长corr窗口"),
    ("B11v_corr10_d10",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 10))",
     "10日量价corr的10日变化 — 长delta窗口"),
    ("B11v_corr10_d3",
     "rank(ts_delta(ts_corr(rank(close), rank(volume), 10), 3))",
     "10日量价corr的3日变化 — 短delta窗口"),
    ("B12v_vol_delta_x_close_delta",
     "rank(ts_delta(ts_rank(volume, 20), 5) * rank(ts_delta(close, 5)))",
     "volume rank变化 × 价格变化 — 量价双因子组合"),
]

ALL_FACTORS = {"A": A_FACTORS, "B": B_FACTORS}
TARGET_SC = 0.3


def compute_expr_hash(expression: str, settings: dict) -> str:
    return hashlib.md5(f"{expression}|{json.dumps(settings, sort_keys=True)}".encode()).hexdigest()


def ensure_db(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alphas (
            expr_hash TEXT PRIMARY KEY, expression TEXT NOT NULL,
            factor_name TEXT, category TEXT, settings_json TEXT NOT NULL,
            alpha_id TEXT, status TEXT DEFAULT 'PENDING',
            sharpe REAL, fitness REAL, ic REAL, rank_ic REAL,
            turnover REAL, annual_return REAL, max_drawdown REAL,
            is_summary TEXT, yearly_json TEXT, submitted_at TEXT,
            completed_at TEXT, error TEXT, progress_url TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submit_checks (
            alpha_id TEXT PRIMARY KEY, factor_name TEXT, checked_at TEXT,
            status TEXT, self_correlation REAL, sharpe REAL, fitness REAL,
            turnover REAL, checks_json TEXT, passed INTEGER DEFAULT 0,
            submitted INTEGER DEFAULT 0, submit_result TEXT, error TEXT
        )
    """)
    conn.commit()
    conn.close()


def is_already_simulated(db_path: str, expression: str, settings: dict, factor_name: str) -> bool:
    expr_hash = compute_expr_hash(expression, settings)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT alpha_id, status FROM alphas WHERE expr_hash = ?", (expr_hash,)
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

    existing = conn.execute("SELECT expr_hash FROM alphas WHERE expr_hash = ?", (expr_hash,)).fetchone()
    if existing:
        conn.execute("""UPDATE alphas SET alpha_id=?, status='COMPLETED', sharpe=?, fitness=?,
            annual_return=?, max_drawdown=?, turnover=?, is_summary=?, completed_at=?
            WHERE expr_hash=?""", (alpha_id, sharpe, fitness, annual_return, max_drawdown,
            turnover, is_summary_json, now, expr_hash))
    else:
        conn.execute("""INSERT INTO alphas (expr_hash, expression, factor_name, category,
            settings_json, alpha_id, status, sharpe, fitness, annual_return, max_drawdown,
            turnover, is_summary, submitted_at) VALUES (?,?,?,?,?,?,'COMPLETED',?,?,?,?,?,?,?)""",
            (expr_hash, expression, factor_name, alpha_type, settings_json, alpha_id,
             sharpe, fitness, annual_return, max_drawdown, turnover, is_summary_json, now))

    existing_check = conn.execute("SELECT alpha_id FROM submit_checks WHERE alpha_id=?", (alpha_id,)).fetchone()
    passed = 1 if sc_result == "PASS" else 0
    if existing_check:
        conn.execute("""UPDATE submit_checks SET factor_name=?, checked_at=?, status=?,
            self_correlation=?, sharpe=?, fitness=?, turnover=?, checks_json=?, passed=?
            WHERE alpha_id=?""", (factor_name, now, sc_result, self_correlation, sharpe,
            fitness, turnover, checks_json, passed, alpha_id))
    else:
        conn.execute("""INSERT INTO submit_checks (alpha_id, factor_name, checked_at, status,
            self_correlation, sharpe, fitness, turnover, checks_json, passed)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (alpha_id, factor_name, now, sc_result,
            self_correlation, sharpe, fitness, turnover, checks_json, passed))
    conn.commit()
    conn.close()


def extract_metrics(result: dict) -> dict:
    alpha_id = result.get("alpha_id")
    if alpha_id is None:
        return {"alpha_id": None, "error": "simulation_failed"}
    is_stats = result.get("is_stats")
    is_tests = result.get("is_tests")
    sharpe = fitness = annual_return = max_drawdown = turnover = None
    if is_stats is not None and not is_stats.empty:
        row = is_stats.iloc[0]
        for col in row.index:
            val = row[col]
            if pd.notna(val):
                if col == "sharpe": sharpe = float(val)
                elif col == "fitness": fitness = float(val)
                elif col == "annualReturn": annual_return = float(val)
                elif col == "maxDrawdown": max_drawdown = float(val)
                elif col == "turnover": turnover = float(val)
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
                except: is_stats_dict[col] = str(val)
    return {"alpha_id": alpha_id, "sharpe": sharpe, "fitness": fitness,
            "annual_return": annual_return, "max_drawdown": max_drawdown, "turnover": turnover,
            "self_correlation": self_correlation, "sc_result": sc_result,
            "checks": checks_list, "is_stats": is_stats_dict}


def submit_batch(session, alpha_list, factor_names, alpha_type, expressions):
    results = ace_lib.simulate_alpha_list(
        session, alpha_list, limit_of_concurrent_simulations=1,
        simulation_config=ace_lib.DEFAULT_CONFIG)
    for i, r in enumerate(results):
        aid = r.get("alpha_id")
        if aid:
            try:
                sc_df = ace_lib.get_self_corr(session, aid)
                if sc_df is not None and not sc_df.empty:
                    sc_value = float(sc_df["correlation"].max())
                    sc_result_str = "PASS" if sc_value < 0.7 else "FAIL"
                    sc_row = pd.DataFrame([{"name": "SELF_CORRELATION", "result": sc_result_str,
                        "value": sc_value, "limit": 0.7, "alpha_id": aid}])
                    if r.get("is_tests") is not None:
                        r["is_tests"] = pd.concat([r["is_tests"], sc_row], ignore_index=True)
                    print(f"  [{factor_names[i]}] SC={sc_value:.4f}")
            except Exception as sc_e:
                print(f"  [{factor_names[i]}] SC获取失败: {sc_e}")
    return results


def generate_report(all_results: list, output_path: str, group_name: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(all_results)
    successful = [r for r in all_results if r.get("alpha_id")]
    sc_pass = [r for r in successful if r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC]
    sharpe_pos = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0]
    candidates = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0.5]

    lines = [f"# WQB SC03 优化回测 v2 — 参数扫描（{group_name}组）",
             f"**生成时间**: {now}",
             f"**回测设置**: EQUITY/USA/TOP3000, delay=1, decay=0, neutralization=SUBINDUSTRY, truncation=0.08, pasteurization=ON, testPeriod=P1Y6M",
             "",
             "## 总体统计",
             "| 指标 | 数值 |",
             "|------|------|",
             f"| 因子总数 | {total} |",
             f"| 回测成功 | {len(successful)}/{total} |",
             f"| SC < {TARGET_SC} | {len(sc_pass)}/{total} |",
             f"| Sharpe > 0 | {len(sharpe_pos)}/{total} |",
             f"| Sharpe > 0.5 候选 | {len(candidates)}/{total} |",
             ""]

    lines.append("## 因子回测结果明细")
    lines.append("| 因子 | 设计思路 | Alpha ID | Sharpe | Fitness | 年化收益 | 最大回撤 | 换手率 | SC | SC<0.3? | Sharpe>0? |")
    lines.append("|------|---------|----------|--------|---------|---------|---------|--------|----|--------|----------|")
    for r in all_results:
        name = r["factor_name"]
        desc = r.get("design_desc", "")
        aid = r.get("alpha_id") or "FAILED"
        sh_s = f"{r['sharpe']:.4f}" if r.get("sharpe") is not None else "N/A"
        ft_s = f"{r['fitness']:.4f}" if r.get("fitness") is not None else "N/A"
        ret_s = f"{r['annual_return']*100:.2f}%" if r.get("annual_return") is not None else "N/A"
        dd_s = f"{r['max_drawdown']*100:.2f}%" if r.get("max_drawdown") is not None else "N/A"
        to_s = f"{r['turnover']:.2f}" if r.get("turnover") is not None else "N/A"
        sc_s = f"{r['self_correlation']:.4f}" if r.get("self_correlation") is not None else "N/A"
        sc_ok = r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC
        sp_ok = r.get("sharpe") is not None and r["sharpe"] > 0
        lines.append(f"| {name} | {desc} | {aid} | {sh_s} | {ft_s} | {ret_s} | {dd_s} | {to_s} | {sc_s} | {'✅' if sc_ok else '❌'} | {'✅' if sp_ok else '❌'} |")

    lines.append("")
    if candidates:
        lines.append("## 候选因子 (Sharpe > 0.5)")
        lines.append("| 排名 | 因子 | Sharpe | Fitness | SC | 回撤 |")
        lines.append("|------|------|--------|---------|-----|------|")
        for rank, r in enumerate(sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True), 1):
            sh = r.get('sharpe') or 0
            ft = r.get('fitness') or 0
            sc = r.get('self_correlation') or 0
            dd = (r.get('max_drawdown') or 0) * 100
            lines.append(f"| {rank} | {r['factor_name']} | {sh:.4f} | {ft:.4f} | {sc:.4f} | {dd:.2f}% |")
        lines.append("")

    lines.append("## 各因子详细结果")
    for r in all_results:
        aid = r.get("alpha_id")
        if not aid: continue
        lines.append(f"### {r['factor_name']}")
        lines.append(f"- **表达式**: `{r.get('expression', 'N/A')}`")
        lines.append(f"- **设计思路**: {r.get('design_desc', 'N/A')}")
        lines.append(f"- **Alpha ID**: {aid}")
        lines.append(f"- **Sharpe**: {r['sharpe']:.4f}" if r.get("sharpe") is not None else "- **Sharpe**: N/A")
        lines.append(f"- **SC**: {r['self_correlation']:.4f}" if r.get("self_correlation") is not None else "- **SC**: N/A")
        lines.append("")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return "\n".join(lines)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-mode", default="display_only", choices=["display_only", "notify", "no_reply", "auto"])
    parser.add_argument("--db-path", default=_DB_PATH)
    parser.add_argument("--report", default=os.path.join(_OUTPUT_DIR, "wqb_sc03_optimize_v2.md"))
    parser.add_argument("--group", default="all", choices=["all", "A", "B"])
    args = parser.parse_args()

    result_mode = args.result_mode
    if result_mode == "auto": result_mode = "display_only"

    sdk = CodeActSDK()
    try:
        print(f"[WQB] 开始SC03优化v2回测...")
        ensure_db(args.db_path)
        print("[WQB] 登录WQB平台...")
        s = ace_lib.start_session()
        timeout = ace_lib.check_session_timeout(s)
        print(f"[WQB] 登录成功，会话有效期: {timeout/3600:.1f} 小时")
        all_results = []

        def process_group(factors, group_name):
            nonlocal all_results
            print(f"\n{'='*60}\n[WQB] {group_name}组: {len(factors)}个因子\n{'='*60}")
            alpha_list, names, exprs, descs = [], [], [], []
            for name, expr, desc in factors:
                if is_already_simulated(args.db_path, expr, BT_SETTINGS, name):
                    conn = sqlite3.connect(args.db_path)
                    row = conn.execute("SELECT alpha_id, sharpe, fitness, annual_return, max_drawdown, turnover, is_summary FROM alphas WHERE expr_hash=?",
                        (compute_expr_hash(expr, BT_SETTINGS),)).fetchone()
                    conn.close()
                    if row and row[0]:
                        metrics = {"alpha_id": row[0], "sharpe": row[1], "fitness": row[2],
                            "annual_return": row[3], "max_drawdown": row[4], "turnover": row[5],
                            "self_correlation": None, "sc_result": "UNKNOWN", "checks": [],
                            "is_stats": json.loads(row[6]) if row[6] else {},
                            "factor_name": name, "alpha_type": group_name, "expression": expr, "design_desc": desc}
                        try:
                            conn = sqlite3.connect(args.db_path)
                            sc_row = conn.execute("SELECT correlation FROM self_corr WHERE alpha_id=? ORDER BY fetched_at DESC LIMIT 1", (row[0],)).fetchone()
                            conn.close()
                            if sc_row: metrics["self_correlation"] = sc_row[0]
                        except: pass
                        all_results.append(metrics)
                    continue
                sim_data = ace_lib.generate_alpha(regular=expr, alpha_type="REGULAR",
                    region=BT_SETTINGS["region"], universe=BT_SETTINGS["universe"],
                    delay=BT_SETTINGS["delay"], decay=BT_SETTINGS["decay"],
                    neutralization=BT_SETTINGS["neutralization"], truncation=BT_SETTINGS["truncation"],
                    pasteurization=BT_SETTINGS["pasteurization"], test_period=BT_SETTINGS["testPeriod"])
                alpha_list.append(sim_data); names.append(name); exprs.append(expr); descs.append(desc)
                print(f"  [{name}] {expr}")
            if not alpha_list:
                print(f"  [{group_name}组] 所有因子已存在")
                return
            print(f"\n[WQB] 提交{group_name}组回测...")
            batch_results = submit_batch(s, alpha_list, names, group_name, exprs)
            for i, (name, expr, desc) in enumerate(factors):
                r = batch_results[i] if i < len(batch_results) else {"alpha_id": None}
                metrics = extract_metrics(r)
                metrics.update({"factor_name": name, "alpha_type": group_name, "expression": expr, "design_desc": desc})
                if metrics.get("alpha_id"):
                    save_alpha_result(args.db_path, name, expr, group_name, metrics["alpha_id"],
                        BT_SETTINGS, metrics.get("sharpe"), metrics.get("fitness"),
                        metrics.get("annual_return"), metrics.get("max_drawdown"),
                        metrics.get("turnover"), metrics.get("self_correlation"),
                        metrics.get("sc_result", "UNKNOWN"), metrics.get("is_stats", {}), metrics.get("checks", []))
                all_results.append(metrics)
                status = "✅" if metrics["alpha_id"] else "❌"
                sp_str = f"Sharpe={metrics['sharpe']:.4f}" if metrics.get("sharpe") is not None else "Sharpe=N/A"
                sc_str = f"SC={metrics['self_correlation']:.4f}" if metrics.get("self_correlation") is not None else "SC=N/A"
                print(f"  [{name}] {status} | {sp_str} | {sc_str}")

        if args.group in ("all", "A"):
            process_group(A_FACTORS, "A")
            if args.group == "all":
                print("\n[WQB] A组完成，等待120秒后开始B组...")
                time.sleep(120)
        if args.group in ("all", "B"):
            process_group(B_FACTORS, "B")

        if all_results:
            group_name = args.group.upper() if args.group != "all" else "ALL"
            print(f"\n[WQB] 生成报告...")
            report_text = generate_report(all_results, args.report, group_name)
            abs_report_path = os.path.abspath(args.report)
            print(f"[WQB] 报告已保存到: {abs_report_path}")

            successful = [r for r in all_results if r.get("alpha_id")]
            sc_pass = [r for r in successful if r.get("self_correlation") is not None and r["self_correlation"] < TARGET_SC]
            sharpe_pos = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0]
            candidates = [r for r in successful if r.get("sharpe") is not None and r["sharpe"] > 0.5]

            print(f"\n{'='*60}\n[WQB] 执行完成")
            print(f"  成功: {len(successful)}/{len(all_results)}")
            print(f"  SC<{TARGET_SC}: {len(sc_pass)}/{len(all_results)}")
            print(f"  Sharpe>0: {len(sharpe_pos)}/{len(all_results)}")
            print(f"  Sharpe>0.5候选: {len(candidates)}")
            print(f"{'='*60}")

            msg_lines = [f"WQB SC03优化v2回测完成 — {group_name}组",
                f"**成功回测**: {len(successful)}/{len(all_results)}",
                f"**SC<{TARGET_SC}**: {len(sc_pass)}/{len(all_results)}",
                f"**Sharpe>0**: {len(sharpe_pos)}/{len(all_results)}",
                f"**Sharpe>0.5候选**: {len(candidates)}", ""]
            if sc_pass:
                msg_lines.append("**SC<0.3因子:**")
                for r in sorted(sc_pass, key=lambda x: x.get("sharpe") or 0, reverse=True):
                    msg_lines.append(f"  - {r['factor_name']}: Sharpe={r.get('sharpe','N/A'):.4f}, SC={r.get('self_correlation','N/A'):.4f}")
            if candidates:
                msg_lines.append("")
                msg_lines.append("**候选因子 (Sharpe>0.5):**")
                for r in sorted(candidates, key=lambda x: x.get("sharpe") or 0, reverse=True):
                    msg_lines.append(f"  - {r['factor_name']}: Sharpe={r.get('sharpe','N/A'):.4f}, SC={r.get('self_correlation','N/A'):.4f}")
            msg_lines.append(f"\n完整报告: [wqb_sc03_optimize_v2.md](computer://{abs_report_path})")

            await sdk.submit_result(result_mode=result_mode, status="success",
                message="\n".join(msg_lines),
                data={"report_path": args.report, "total": len(all_results),
                    "successful": len(successful), "sc_pass": len(sc_pass),
                    "sharpe_pos": len(sharpe_pos), "candidates": len(candidates)})
        else:
            await sdk.submit_result(result_mode="display_only", status="success",
                message="无因子需要回测。", data={"skipped": True})
    except Exception as e:
        print(f"[WQB] 执行失败: {e}")
        import traceback; traceback.print_exc()
        await sdk.submit_result(result_mode="notify", status="error",
            message=f"WQB SC03优化v2回测执行失败: {e}",
            data={"error_type": type(e).__name__, "error": str(e)})

if __name__ == "__main__":
    asyncio.run(main())