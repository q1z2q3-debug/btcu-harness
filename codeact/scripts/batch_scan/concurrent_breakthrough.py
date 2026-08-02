#!/usr/bin/env python3
"""
Concurrent Breakthrough Sweep - 一次登录，参数扫描并发版
Decay扫描 + Neutralization扫描，复用session
"""

import os, sys, json, time, hashlib, argparse
from datetime import datetime
from pathlib import Path

for v in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(v, None)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ace_lib'))
import ace_lib

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 18 best volume delta / volume ratio expressions from SC03 testing
BASE_EXPRESSIONS = [
    "rank(ts_delta(ts_rank(volume,10),3))",
    "rank(volume/ts_mean(volume,20))",
    "rank(ts_delta(ts_rank(volume,20),3))",
    "rank(ts_delta(ts_rank(volume,30),3))",
    "rank(ts_delta(ts_rank(volume,10),5))",
    "rank(volume/ts_mean(volume,10))",
    "rank(volume/ts_mean(volume,40))",
    "rank(volume/ts_mean(volume,60))",
    "rank(ts_delta(ts_delta(ts_rank(volume,10),3),3))",
    "rank(ts_delta(ts_delta(ts_rank(volume,20),5),5))",
    "rank(ts_delta(ts_rank(volume,10),3) * rank(ts_std(close,20)))",
    "rank(volume/ts_mean(volume,20) * rank(ts_std(close,20)))",
    "rank(ts_mean(volume,5)/ts_mean(volume,20))",
    "rank(ts_mean(volume,5)/ts_mean(volume,60))",
    "rank(ts_corr(volume, ts_mean(volume,20), 10))",
    "rank(ts_corr(ts_delta(volume,1), ts_delta(volume,5), 10))",
    "rank(ts_corr(rank(close), rank(volume), 10))",
    "rank(ts_corr(rank(ts_delta(close,1)), rank(ts_delta(volume,1)), 10))",
]

DECAY_VALUES = [0, 1, 3, 5, 10, 15]
NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET_EQUITY"]

def run_batch(s, expressions, names, decay, neut, config):
    """Run a batch of simulations with given settings."""
    name_map = {expr: name for expr, name in zip(expressions, names)}
    alpha_list = []
    for expr in expressions:
        sim_data = ace_lib.generate_alpha(
            regular=expr,
            region="USA", universe="TOP3000",
            delay=1, decay=decay, neutralization=neut,
            truncation=0.08, pasteurization="ON",
            test_period="P1Y6M", unit_handling="VERIFY",
            nan_handling="OFF", max_trade="OFF",
            visualization=False,
        )
        alpha_list.append(sim_data)
    
    results = ace_lib.simulate_alpha_list(
        s=s, alpha_list=alpha_list,
        limit_of_concurrent_simulations=3,
        simulation_config=config,
    )
    return results, name_map

def parse_results(results, name_map):
    """Parse ACE simulation results into a clean list."""
    parsed = []
    for r in results:
        if r.get("alpha_id") is None:
            continue
        expr = r["simulate_data"].get("regular", "")
        entry = {
            "factor_name": name_map.get(expr, "?"),
            "expression": expr,
            "alpha_id": r["alpha_id"],
            "sharpe": None, "fitness": None, "turnover": None, "self_correlation": None,
        }
        stats = r.get("is_stats")
        if stats is not None and not stats.empty:
            if isinstance(stats, dict):
                entry["sharpe"] = stats.get("sharpe")
                entry["fitness"] = stats.get("fitness")
                entry["turnover"] = stats.get("turnover")
                entry["retention"] = stats.get("retention")
                entry["max_drawdown"] = stats.get("maxDrawdown")
            else:
                # pandas DataFrame/series: try to access as dict-like
                for col in ["sharpe", "fitness", "turnover", "retention", "maxDrawdown"]:
                    if col in stats:
                        val = stats[col]
                        entry[col.replace("maxDrawdown", "max_drawdown")] = float(val) if hasattr(val, '__float__') else val
        
        tests = r.get("is_tests")
        if tests is not None and not tests.empty:
            sc_row = tests[tests["test"] == "SELF_CORRELATION"]
            if not sc_row.empty:
                entry["self_correlation"] = float(sc_row.iloc[0]["value"])
        
        parsed.append(entry)
    return parsed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="all", choices=["decay", "neut", "all"])
    parser.add_argument("--result-mode", default="display_only", choices=["display_only","notify","no_reply","auto"])
    args = parser.parse_args()
    
    config = {"get_pnl": False, "get_stats": False, "check_submission": True, "check_self_corr": True, "check_prod_corr": False}
    all_results = []
    
    # ONE login
    print("[CONCURRENT_BREAK] 登录中...")
    s = ace_lib.start_session()
    print("[CONCURRENT_BREAK] 登录成功，开始扫描")
    
    if args.mode in ("decay", "all"):
        print("\n" + "=" * 70)
        print(f"SWEEP 1: Decay扫描 ({len(BASE_EXPRESSIONS)}表达式 × {len(DECAY_VALUES)}种decay)")
        print("=" * 70)
        
        for decay in DECAY_VALUES:
            names = [f"d{decay}_e{i+1}" for i in range(len(BASE_EXPRESSIONS))]
            print(f"\n--- Decay={decay} ---")
            results, name_map = run_batch(s, BASE_EXPRESSIONS, names, decay, "SUBINDUSTRY", config)
            parsed = parse_results(results, name_map)
            all_results.append({"type": "decay", "value": decay, "results": parsed})
            
            for r in sorted(parsed, key=lambda x: x.get("sharpe") or -999, reverse=True)[:5]:
                sh = r.get("sharpe", "N/A")
                sc = r.get("self_correlation", "N/A")
                sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
                sh_str = f"{sh:.4f}" if isinstance(sh, (int,float)) else str(sh)
                print(f"  {r['factor_name'][:25]:<25} S={sh_str} SC={sc_str}")
            
            # Sleep between batches to let simulations settle and avoid concurrent limit
            if decay != DECAY_VALUES[-1]:
                print(f"  [等待60秒避免并发限流...]")
                time.sleep(60)
    
    if args.mode in ("neut", "all"):
        print("\n" + "=" * 70)
        print(f"SWEEP 2: Neutralization扫描 (5表达式 × {len(NEUTRALIZATIONS)}种neut)")
        print("=" * 70)
        
        best_exprs = BASE_EXPRESSIONS[:5]
        for neut in NEUTRALIZATIONS:
            names = [f"neut_{neut[:4]}_e{i+1}" for i in range(len(best_exprs))]
            print(f"\n--- Neutralization={neut} ---")
            results, name_map = run_batch(s, best_exprs, names, 0, neut, config)
            parsed = parse_results(results, name_map)
            all_results.append({"type": "neut", "value": neut, "results": parsed})
            
            for r in sorted(parsed, key=lambda x: x.get("sharpe") or -999, reverse=True):
                sh = r.get("sharpe", "N/A")
                sc = r.get("self_correlation", "N/A")
                sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
                sh_str = f"{sh:.4f}" if isinstance(sh, (int,float)) else str(sh)
                print(f"  {r['factor_name'][:25]:<25} S={sh_str} SC={sc_str}")
    
    # Final summary
    flat = [r for sweep in all_results for r in sweep["results"]]
    
    print("\n" + "=" * 70)
    print("突破方向 - 最终汇总")
    print("=" * 70)
    
    sc03 = [r for r in flat if isinstance(r.get("self_correlation"), (int,float)) and r["self_correlation"] < 0.3]
    high_sh = [r for r in flat if r.get("sharpe") and r["sharpe"] > 1.0]
    
    print(f"\nSC<0.3 候选: {len(sc03)} 个")
    for r in sorted(sc03, key=lambda x: x["sharpe"] or -999, reverse=True):
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={r['self_correlation']:.4f}")
    
    print(f"\nSharpe>1.0 候选: {len(high_sh)} 个")
    for r in sorted(high_sh, key=lambda x: x["sharpe"] or -999, reverse=True):
        sc = r.get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
        print(f"  {r['factor_name'][:25]:<25} S={r['sharpe']:.4f} SC={sc_str}")
    
    # Save report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"concurrent_breakthrough_{timestamp}.md")
    with open(report_path, "w") as f:
        f.write(f"# 并发突破方向参数扫描报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## SC<0.3 候选\n\n")
        f.write(f"| 因子名 | Sharpe | SC | 换手率 | Fitness |\n")
        f.write(f"|-------|--------|----|--------|--------|\n")
        for r in sorted(sc03, key=lambda x: x["sharpe"] or -999, reverse=True):
            f.write(f"| {r['factor_name']} | {r['sharpe']:.4f} | {r['self_correlation']:.4f} | {r.get('turnover','N/A')} | {r.get('fitness','N/A')} |\n")
        f.write(f"\n## Sharpe>1.0 候选\n\n")
        f.write(f"| 因子名 | Sharpe | SC | 换手率 | Fitness |\n")
        f.write(f"|-------|--------|----|--------|--------|\n")
        for r in sorted(high_sh, key=lambda x: x["sharpe"] or -999, reverse=True):
            sc = r.get("self_correlation", "N/A")
            sc_str = f"{sc:.4f}" if isinstance(sc, (int,float)) else str(sc)
            f.write(f"| {r['factor_name']} | {r['sharpe']:.4f} | {sc_str} | {r.get('turnover','N/A')} | {r.get('fitness','N/A')} |\n")
    
    json_path = report_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump({
            "sc03_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r["self_correlation"]} for r in sc03],
            "high_sharpe_candidates": [{"name": r["factor_name"], "sharpe": r["sharpe"], "sc": r.get("self_correlation")} for r in high_sh],
        }, f, indent=2)
    
    print(f"\n报告: {report_path}")
    print(f"JSON: {json_path}")

if __name__ == "__main__":
    main()