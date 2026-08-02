#!/usr/bin/env python3
"""
ACE Mass Scan - 60+ expressions across 4 categories
Uses ace_batch_runner.py to batch test, then ranks results
"""
import os, sys, json, time, argparse
from pathlib import Path

# Add parent to path for ace_batch_runner
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

from ace_batch_runner import ACEBatchRunner, DB_PATH, OUTPUT_DIR, generate_report

CATEGORIES = {
    "A_volume": "expressions_category_A_volume.txt",
    "B_corr": "expressions_category_B_corr.txt",
    "C_nonlinear": "expressions_category_C_nonlinear.txt",
    "D_price": "expressions_category_D_price.txt",
}

def load_all_expressions(base_dir: str) -> tuple:
    """Load all expressions from category files."""
    all_exprs = []
    all_names = []
    cat_map = {}
    
    for cat, filename in CATEGORIES.items():
        filepath = os.path.join(base_dir, filename)
        if not os.path.exists(filepath):
            print(f"[WARN] {filepath} not found, skip")
            continue
        
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name = f"{cat}_{len([e for e in all_exprs if e.startswith(cat)]) + 1}"
                all_exprs.append(line)
                all_names.append(name)
                cat_map[name] = cat
    
    return all_exprs, all_names, cat_map


def main():
    parser = argparse.ArgumentParser(description="ACE Mass Scan")
    parser.add_argument("--region", default="USA")
    parser.add_argument("--universe", default="TOP3000")
    parser.add_argument("--delay", type=int, default=1)
    parser.add_argument("--decay", type=int, default=0)
    parser.add_argument("--neutralization", default="INDUSTRY")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--result-mode", default="display_only", choices=["display_only", "notify", "no_reply", "auto"])
    args = parser.parse_args()
    
    # Load expressions
    base_dir = os.path.dirname(os.path.abspath(__file__))
    expressions, names, cat_map = load_all_expressions(base_dir)
    print(f"[MASS_SCAN] 加载 {len(expressions)} 个因子表达式")
    for i, (expr, name) in enumerate(zip(expressions, names)):
        print(f"  [{i+1:02d}] {name}: {expr}")
    
    # Settings
    settings = {
        "instrumentType": "EQUITY",
        "region": args.region,
        "universe": args.universe,
        "delay": args.delay,
        "decay": args.decay,
        "neutralization": args.neutralization,
        "truncation": 0.08,
        "pasteurization": "ON",
        "testPeriod": "P1Y6M",
        "unitHandling": "VERIFY",
        "nanHandling": "OFF",
        "language": "FASTEXPR",
    }
    
    # Create runner
    runner = ACEBatchRunner(
        db_path=DB_PATH,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        auto_submit=False,
        settings=settings,
    )
    
    # Run
    runner.login()
    result = runner.run(expressions, names)
    
    # Generate report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"ace_mass_scan_{timestamp}.md")
    report = generate_report(
        result["results"],
        result["submitted"],
        result["summary"],
        output_path=report_path,
    )
    
    # Print ranked results
    print("\n" + "=" * 70)
    print("MASS SCAN 完成 - 最佳候选因子排名")
    print("=" * 70)
    
    # Sort by Sharpe descending
    ranked = sorted(
        [r for r in result["results"] if r.get("submit_check")],
        key=lambda r: r["submit_check"].get("sharpe", -999) or -999,
        reverse=True
    )
    
    print(f"\n{'排名':<4} {'因子名':<25} {'Sharpe':<8} {'Fitness':<8} {'SC':<8} {'换手率':<8} {'状态':<10}")
    print("-" * 75)
    
    for i, r in enumerate(ranked):
        sc = r["submit_check"].get("self_correlation", "N/A")
        sc_str = f"{sc:.4f}" if isinstance(sc, (int, float)) else str(sc)
        sh = r["submit_check"].get("sharpe", "N/A")
        sh_str = f"{sh:.4f}" if isinstance(sh, (int, float)) else str(sh)
        ft = r["submit_check"].get("fitness", "N/A")
        ft_str = f"{ft:.4f}" if isinstance(ft, (int, float)) else str(ft)
        to = r["submit_check"].get("turnover", "N/A")
        to_str = f"{to:.4f}" if isinstance(to, (int, float)) else str(to)
        st = r["submit_check"].get("status", "N/A")
        
        print(f"{i+1:<4} {r.get('factor_name', '?')[:25]:<25} {sh_str:<8} {ft_str:<8} {sc_str:<8} {to_str:<8} {st:<10}")
    
    print(f"\n报告: {report_path}")
    
    # Critical: output SC<0.3 candidates
    low_sc = [r for r in ranked if isinstance(r["submit_check"].get("self_correlation"), (int, float)) 
              and r["submit_check"]["self_correlation"] < 0.3]
    high_sh = [r for r in ranked if isinstance(r["submit_check"].get("sharpe"), (int, float))
               and r["submit_check"]["sharpe"] > 1.25]
    
    print(f"\n=== SC<0.3 候选: {len(low_sc)} 个 ===")
    for r in low_sc:
        print(f"  {r.get('factor_name','?'):<25} S={r['submit_check'].get('sharpe','N/A')} F={r['submit_check'].get('fitness','N/A')} SC={r['submit_check'].get('self_correlation','N/A')} TO={r['submit_check'].get('turnover','N/A')}")
    
    print(f"\n=== Sharpe>1.25 候选: {len(high_sh)} 个 ===")
    for r in high_sh:
        print(f"  {r.get('factor_name','?'):<25} S={r['submit_check'].get('sharpe','N/A')} F={r['submit_check'].get('fitness','N/A')} SC={r['submit_check'].get('self_correlation','N/A')} TO={r['submit_check'].get('turnover','N/A')}")
    
    # Save ranked results to JSON
    json_path = os.path.join(OUTPUT_DIR, f"ace_mass_scan_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump({
            "summary": result["summary"],
            "ranked": [{
                "factor_name": r.get("factor_name", "?"),
                "alpha_id": r.get("alpha_id"),
                "sharpe": r["submit_check"].get("sharpe") if r.get("submit_check") else None,
                "fitness": r["submit_check"].get("fitness") if r.get("submit_check") else None,
                "self_correlation": r["submit_check"].get("self_correlation") if r.get("submit_check") else None,
                "turnover": r["submit_check"].get("turnover") if r.get("submit_check") else None,
                "status": r["submit_check"].get("status") if r.get("submit_check") else None,
            } for r in ranked],
            "low_sc_candidates": [r.get("factor_name") for r in low_sc],
            "high_sharpe_candidates": [r.get("factor_name") for r in high_sh],
        }, f, indent=2, ensure_ascii=False)
    print(f"\nJSON: {json_path}")


if __name__ == "__main__":
    main()