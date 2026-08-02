#!/usr/bin/env python3
"""
Concurrent Mass Scan - ACE库simulate_alpha_list直接调用
一次登录，复用session，3并发线程，避开重复登录限流
"""

import os, sys, json, time, hashlib, argparse, threading
from datetime import datetime
from pathlib import Path
from functools import partial

for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib'))
import ace_lib

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

CATEGORIES = {
    "A_volume": "expressions_category_A_volume.txt",
    "B_corr": "expressions_category_B_corr.txt",
    "C_nonlinear": "expressions_category_C_nonlinear.txt",
    "D_price": "expressions_category_D_price.txt",
}

BASE_SETTINGS = {
    "instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000",
    "delay": 1, "decay": 0, "neutralization": "SUBINDUSTRY",
    "truncation": 0.08, "pasteurization": "ON", "testPeriod": "P1Y6M",
    "unitHandling": "VERIFY", "nanHandling": "OFF", "maxTrade": "OFF",
    "language": "FASTEXPR", "visualization": False,
}

def load_expressions(base_dir):
    all_exprs, all_names = [], []
    for cat, filename in CATEGORIES.items():
        fp = os.path.join(base_dir, filename)
        if not os.path.exists(fp): continue
        with open(fp) as f:
            n = 0
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                n += 1
                all_exprs.append(line)
                all_names.append(f"{cat}_{n}")
    return all_exprs, all_names

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-mode", default="display_only", choices=["display_only","notify","no_reply","auto"])
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    expressions, names = load_expressions(base_dir)
    total = len(expressions)
    print(f"[CONCURRENT] 加载 {total} 个因子表达式")
    
    # ONE login - get a fresh session
    print("[CONCURRENT] 登录中...")
    s = ace_lib.start_session()
    print("[CONCURRENT] 登录成功")
    
    # Build alpha configs (no extra fields - sent directly to API)
    name_map = {}  # expr -> name mapping for result lookup
    alpha_list = []
    for expr, name in zip(expressions, names):
        sim_data = ace_lib.generate_alpha(
            regular=expr,
            region="USA", universe="TOP3000",
            delay=1, decay=0, neutralization="SUBINDUSTRY",
            truncation=0.08, pasteurization="ON",
            test_period="P1Y6M", unit_handling="VERIFY",
            nan_handling="OFF", max_trade="OFF",
            visualization=False,
        )
        name_map[expr] = name
        alpha_list.append(sim_data)
    
    # Simulate using ACE's concurrent engine
    # limit_of_concurrent_simulations=3 means 3 threads
    # Each thread uses the SAME session object
    print(f"[CONCURRENT] 开始并发回测 ({len(alpha_list)} 因子, 3并发)...")
    config = {"get_pnl": False, "get_stats": False, "check_submission": True, "check_self_corr": True, "check_prod_corr": False}
    
    results = ace_lib.simulate_alpha_list(
        s=s,
        alpha_list=alpha_list,
        limit_of_concurrent_simulations=3,
        simulation_config=config,
    )
    
    print(f"\n[CONCURRENT] 回测完成: {len(results)} 个结果")
    
    # Parse results
    parsed = []
    success_count = 0
    for r in results:
        if r.get("alpha_id") is None:
            continue
        success_count += 1
        
        expr = r["simulate_data"].get("regular", "")
        entry = {
            "factor_name": name_map.get(expr, "?"),
            "expression": expr,
            "alpha_id": r["alpha_id"],
            "sharpe": None, "fitness": None, "turnover": None, "self_correlation": None,
        }
        
        # Get stats from is_stats
        stats = r.get("is_stats")
        if stats is not None:
            if isinstance(stats, dict):
                entry["sharpe"] = stats.get("sharpe")
                entry["fitness"] = stats.get("fitness")
                entry["turnover"] = stats.get("turnover")
                entry["retention"] = stats.get("retention")
                entry["max_drawdown"] = stats.get("maxDrawdown")
            elif hasattr(stats, 'empty') and not stats.empty:
                # pandas DataFrame
                for col in ["sharpe", "fitness", "turnover", "retention", "maxDrawdown"]:
                    if col in stats:
                        val = stats[col]
                        entry[col.replace("maxDrawdown", "max_drawdown")] = float(val) if hasattr(val, '__float__') else val
        
        # Get SC from is_tests
        tests = r.get("is_tests")
        if tests is not None and not tests.empty:
            sc_row = tests[tests["test"] == "SELF_CORRELATION"]
            if not sc_row.empty:
                entry["self_correlation"] = float(sc_row.iloc[0]["value"])
        
        parsed.append(entry)
    
    # Report
    print("\n" + "=" * 70)
    print(f"CONCURRENT SCAN 完成: {success_count}/{total} 成功")
    print("=" * 70)
    
    ranked = sorted([r for r in parsed if r.get("sharpe") is not None],
                    key=lambda r: r["sharpe"], reverse=True)
    
    print(f"\n{'排名':<4} {'因子名':<25} {'Sharpe':<8} {'Fitness':<8} {'SC':<8} {'换手率':<8}")
    print("-" * 65)
    for i, r in enumerate(ranked):
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        sh_str = f"{r['sharpe']:.4f}" if r.get("sharpe") else "N/A"
        ft_str = f"{r['fitness']:.4f}" if r.get("fitness") else "N/A"
        to_str = f"{r['turnover']:.4f}" if r.get("turnover") else "N/A"
        print(f"{i+1:<4} {r['factor_name'][:25]:<25} {sh_str:<8} {ft_str:<8} {sc_str:<8} {to_str:<8}")
    
    low_sc = [r for r in ranked if isinstance(r.get("self_correlation"), (int,float)) and r["self_correlation"] < 0.3]
    print(f"\n=== SC<0.3 候选: {len(low_sc)} 个 ===")
    for r in sorted(low_sc, key=lambda x: x["sharpe"] or -999, reverse=True):
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={r['self_correlation']:.4f}")
    
    high_sh = [r for r in ranked if r.get("sharpe") and r["sharpe"] > 1.25]
    print(f"\n=== Sharpe>1.25 候选: {len(high_sh)} 个 ===")
    for r in high_sh:
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={sc_str}")
    
    # Save report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"concurrent_mass_scan_{timestamp}.md")
    with open(report_path, "w") as f:
        f.write(f"# Concurrent Mass Scan 报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**成功/总数**: {success_count}/{total}\n\n")
        f.write(f"## 全量排名\n\n")
        f.write(f"| 排名 | 因子名 | Sharpe | Fitness | SC | 换手率 |\n")
        f.write(f"|------|--------|--------|---------|----|--------|\n")
        for i, r in enumerate(ranked):
            sc = r.get("self_correlation", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            sh_str = f"{r['sharpe']:.4f}" if r.get("sharpe") else "N/A"
            ft_str = f"{r['fitness']:.4f}" if r.get("fitness") else "N/A"
            to_str = f"{r['turnover']:.4f}" if r.get("turnover") else "N/A"
            f.write(f"| {i+1} | {r['factor_name']} | {sh_str} | {ft_str} | {sc_str} | {to_str} |\n")
        f.write(f"\n## SC<0.3 候选\n\n")
        for r in low_sc:
            sc_str = f"{r['self_correlation']:.4f}" if isinstance(r.get("self_correlation"), (int,float)) else "N/A"
            f.write(f"- {r['factor_name']}: S={r['sharpe']:.4f} SC={sc_str}\n")
        f.write(f"\n## Sharpe>1.25 候选\n\n")
        for r in high_sh:
            sc = r.get("self_correlation", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            f.write(f"- {r['factor_name']}: S={r['sharpe']:.4f} SC={sc_str}\n")
    
    json_path = report_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump({
            "success_count": success_count, "total": total,
            "ranked": [{"name": r["factor_name"], "sharpe": r.get("sharpe"), "sc": r.get("self_correlation"), "fitness": r.get("fitness"), "turnover": r.get("turnover")} for r in ranked],
            "sc03_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r["self_correlation"]} for r in low_sc],
            "high_sharpe_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r.get("self_correlation")} for r in high_sh],
        }, f, indent=2)
    
    print(f"\n报告: {report_path}")
    print(f"JSON: {json_path}")

if __name__ == "__main__":
    main()