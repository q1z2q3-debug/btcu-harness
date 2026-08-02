#!/usr/bin/env python3
"""
Breakthrough Direction - Parallel to Mass Scan
Focus: parameter sweep on best-known SC<0.3 candidates
- Take best volume delta expressions from SC03 tests
- Sweep decay: 0, 1, 3, 5, 10, 15
- Sweep neutralization: SUBINDUSTRY, INDUSTRY, SECTOR, MARKET_EQUITY
- Goal: find a combination that pushes Sharpe>1.6 while keeping SC<0.3
"""
import os, sys, json, time, argparse
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

from ace_batch_runner import ACEBatchRunner, DB_PATH, OUTPUT_DIR, generate_report, run_submit_check, check_production_correlation, upsert_submit_check, compute_expr_hash, upsert_alpha

# Best volume delta / volume ratio expressions from SC03 testing
# These have proven SC<0.3 potential
BASE_EXPRESSIONS = [
    # SC03 best: volume rank delta (SC=0.156, S=0.70)
    "rank(ts_delta(ts_rank(volume,10),3))",
    # SC03 best: volume ratio (SC=0.312, S=0.71)
    "rank(volume/ts_mean(volume,20))",
    # Extended: volume rank delta with longer windows
    "rank(ts_delta(ts_rank(volume,20),3))",
    "rank(ts_delta(ts_rank(volume,30),3))",
    "rank(ts_delta(ts_rank(volume,10),5))",
    # Extended: volume ratio with different windows
    "rank(volume/ts_mean(volume,10))",
    "rank(volume/ts_mean(volume,40))",
    "rank(volume/ts_mean(volume,60))",
    # Volume acceleration: 2nd derivative
    "rank(ts_delta(ts_delta(ts_rank(volume,10),3),3))",
    "rank(ts_delta(ts_delta(ts_rank(volume,20),5),5))",
    # Volume vs volatility combo
    "rank(ts_delta(ts_rank(volume,10),3) * rank(ts_std(close,20)))",
    "rank(volume/ts_mean(volume,20) * rank(ts_std(close,20)))",
    # Volume-ma-cross (ratio of short/long volume)
    "rank(ts_mean(volume,5)/ts_mean(volume,20))",
    "rank(ts_mean(volume,5)/ts_mean(volume,60))",
    # Volume autocorrelation
    "rank(ts_corr(volume, ts_mean(volume,20), 10))",
    "rank(ts_corr(ts_delta(volume,1), ts_delta(volume,5), 10))",
    # Price-volume cross
    "rank(ts_corr(rank(close), rank(volume), 10))",
    "rank(ts_corr(rank(ts_delta(close,1)), rank(ts_delta(volume,1)), 10))",
]

DECAY_VALUES = [0, 1, 3, 5, 10, 15]
NEUTRALIZATIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET_EQUITY"]

def main():
    parser = argparse.ArgumentParser(description="Breakthrough Sweep")
    parser.add_argument("--mode", default="decay", choices=["decay", "neut", "all"])
    parser.add_argument("--region", default="USA")
    parser.add_argument("--universe", default="TOP3000")
    parser.add_argument("--delay", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--result-mode", default="display_only", choices=["display_only", "notify", "no_reply", "auto"])
    args = parser.parse_args()
    
    results_summary = []
    runner = None
    
    if args.mode in ("decay", "all"):
        # Sweep 1: decay sweep on 18 base expressions
        # Use default neutralization SUBINDUSTRY
        print("=" * 70)
        print(f"SWEEP 1: Decay Sweep ({len(BASE_EXPRESSIONS)} expr × {len(DECAY_VALUES)} decay = {len(BASE_EXPRESSIONS)*len(DECAY_VALUES)} combinations)")
        print("=" * 70)
        
        for decay in DECAY_VALUES:
            settings = {
                "instrumentType": "EQUITY",
                "region": args.region,
                "universe": args.universe,
                "delay": args.delay,
                "decay": decay,
                "neutralization": "SUBINDUSTRY",
                "truncation": 0.08,
                "pasteurization": "ON",
                "testPeriod": "P1Y6M",
                "unitHandling": "VERIFY",
                "nanHandling": "OFF",
                "language": "FASTEXPR",
            }
            
            names = [f"decay{decay}_e{i+1}" for i in range(len(BASE_EXPRESSIONS))]
            
            runner = ACEBatchRunner(
                db_path=DB_PATH,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
                auto_submit=False,
                settings=settings,
            )
            
            if not runner.session:
                runner.login()
            
            result = runner.run(BASE_EXPRESSIONS, names)
            results_summary.append({
                "type": "decay_sweep",
                "value": decay,
                "summary": result["summary"],
                "results": result["results"],
            })
            
            # Print decay sweep results
            print(f"\n--- Decay={decay} 结果 ---")
            for r in sorted(result["results"], 
                          key=lambda x: (x.get("submit_check") or {}).get("sharpe", -999) or -999,
                          reverse=True):
                sc = r.get("submit_check", {})
                sh = sc.get("sharpe", "N/A")
                sc_val = sc.get("self_correlation", "N/A")
                to = sc.get("turnover", "N/A")
                ft = sc.get("fitness", "N/A")
                print(f"  {r.get('factor_name','?'):<25} S={sh} SC={sc_val} TO={to} F={ft}")
    
    if args.mode in ("neut", "all"):
        # Sweep 2: neutralization sweep on best 5 expressions with decay=0
        # Only 5 best expressions to keep API calls manageable
        best_exprs = BASE_EXPRESSIONS[:5]
        best_names = [f"neut_e{i+1}" for i in range(len(best_exprs))]
        
        print("\n" + "=" * 70)
        print(f"SWEEP 2: Neutralization Sweep ({len(best_exprs)} expr × {len(NEUTRALIZATIONS)} neut = {len(best_exprs)*len(NEUTRALIZATIONS)} combinations)")
        print("=" * 70)
        
        for neut in NEUTRALIZATIONS:
            settings = {
                "instrumentType": "EQUITY",
                "region": args.region,
                "universe": args.universe,
                "delay": args.delay,
                "decay": 0,
                "neutralization": neut,
                "truncation": 0.08,
                "pasteurization": "ON",
                "testPeriod": "P1Y6M",
                "unitHandling": "VERIFY",
                "nanHandling": "OFF",
                "language": "FASTEXPR",
            }
            
            runner = ACEBatchRunner(
                db_path=DB_PATH,
                batch_size=args.batch_size,
                concurrency=args.concurrency,
                auto_submit=False,
                settings=settings,
            )
            
            if not runner.session:
                runner.login()
            
            result = runner.run(best_exprs, best_names)
            results_summary.append({
                "type": "neut_sweep",
                "value": neut,
                "summary": result["summary"],
                "results": result["results"],
            })
            
            print(f"\n--- Neutralization={neut} 结果 ---")
            for r in sorted(result["results"],
                          key=lambda x: (x.get("submit_check") or {}).get("sharpe", -999) or -999,
                          reverse=True):
                sc = r.get("submit_check", {})
                sh = sc.get("sharpe", "N/A")
                sc_val = sc.get("self_correlation", "N/A")
                to = sc.get("turnover", "N/A")
                ft = sc.get("fitness", "N/A")
                print(f"  {r.get('factor_name','?'):<25} S={sh} SC={sc_val} TO={to} F={ft}")
    
    # Final summary - find all SC<0.3 candidates
    print("\n" + "=" * 70)
    print("突破方向 - 最终汇总")
    print("=" * 70)
    
    all_results = []
    for sweep in results_summary:
        all_results.extend(sweep["results"])
    
    # Find SC<0.3 candidates
    sc03_candidates = []
    for r in all_results:
        sc = r.get("submit_check", {})
        if isinstance(sc.get("self_correlation"), (int, float)) and sc["self_correlation"] < 0.3:
            sc03_candidates.append(r)
    
    # Find high Sharpe candidates
    high_sh_candidates = []
    for r in all_results:
        sc = r.get("submit_check", {})
        if isinstance(sc.get("sharpe"), (int, float)) and sc["sharpe"] > 1.0:
            high_sh_candidates.append(r)
    
    print(f"\nSC<0.3 候选: {len(sc03_candidates)} 个")
    for r in sorted(sc03_candidates, key=lambda x: x["submit_check"].get("sharpe", -999) or -999, reverse=True):
        sc = r["submit_check"]
        print(f"  {r.get('factor_name','?'):<25} S={sc.get('sharpe','N/A')} SC={sc.get('self_correlation','N/A')} TO={sc.get('turnover','N/A')} F={sc.get('fitness','N/A')}")
    
    print(f"\nSharpe>1.0 候选: {len(high_sh_candidates)} 个")
    for r in sorted(high_sh_candidates, key=lambda x: x["submit_check"].get("sharpe", -999) or -999, reverse=True):
        sc = r["submit_check"]
        print(f"  {r.get('factor_name','?'):<25} S={sc.get('sharpe','N/A')} SC={sc.get('self_correlation','N/A')} TO={sc.get('turnover','N/A')} F={sc.get('fitness','N/A')}")
    
    # Save report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"breakthrough_sweep_{timestamp}.md")
    with open(report_path, "w") as f:
        f.write(f"# 突破方向参数扫描报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 扫描设置\n\n")
        f.write(f"- 基础表达式: {len(BASE_EXPRESSIONS)} 个\n")
        f.write(f"- Decay值: {DECAY_VALUES}\n")
        f.write(f"- Neutralization: {NEUTRALIZATIONS}\n")
        f.write(f"- 总组合数: {len(BASE_EXPRESSIONS)*len(DECAY_VALUES) + 5*len(NEUTRALIZATIONS)}\n\n")
        
        f.write(f"## SC<0.3 候选\n\n")
        f.write(f"| 因子名 | Sharpe | SC | 换手率 | Fitness |\n")
        f.write(f"|-------|--------|----|--------|--------|\n")
        for r in sorted(sc03_candidates, key=lambda x: x["submit_check"].get("sharpe", -999) or -999, reverse=True):
            sc = r["submit_check"]
            f.write(f"| {r.get('factor_name','?')} | {sc.get('sharpe','N/A')} | {sc.get('self_correlation','N/A')} | {sc.get('turnover','N/A')} | {sc.get('fitness','N/A')} |\n")
        
        f.write(f"\n## Sharpe>1.0 候选\n\n")
        f.write(f"| 因子名 | Sharpe | SC | 换手率 | Fitness |\n")
        f.write(f"|-------|--------|----|--------|--------|\n")
        for r in sorted(high_sh_candidates, key=lambda x: x["submit_check"].get("sharpe", -999) or -999, reverse=True):
            sc = r["submit_check"]
            f.write(f"| {r.get('factor_name','?')} | {sc.get('sharpe','N/A')} | {sc.get('self_correlation','N/A')} | {sc.get('turnover','N/A')} | {sc.get('fitness','N/A')} |\n")
    
    print(f"\n报告: {report_path}")
    
    # Save JSON
    json_path = os.path.join(OUTPUT_DIR, f"breakthrough_sweep_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump({
            "sc03_candidates": len(sc03_candidates),
            "high_sharpe_candidates": len(high_sh_candidates),
            "sc03": [{"name": r.get("factor_name"), "sharpe": r["submit_check"].get("sharpe"), "sc": r["submit_check"].get("self_correlation"), "to": r["submit_check"].get("turnover"), "fit": r["submit_check"].get("fitness")} for r in sc03_candidates],
            "high_sh": [{"name": r.get("factor_name"), "sharpe": r["submit_check"].get("sharpe"), "sc": r["submit_check"].get("self_correlation"), "to": r["submit_check"].get("turnover"), "fit": r["submit_check"].get("fitness")} for r in high_sh_candidates],
        }, f, indent=2, ensure_ascii=False)
    print(f"JSON: {json_path}")


from datetime import datetime

if __name__ == "__main__":
    main()