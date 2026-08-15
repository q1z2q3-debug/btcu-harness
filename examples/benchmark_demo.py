"""Benchmark demonstration script.

Run:
    python examples/benchmark_demo.py

This executes the full BTCU benchmark suite and prints a formatted comparison
report showing BTCU advantages over baseline approaches.
"""

from btcu_harness.benchmark.runner import BenchmarkRunner
from btcu_harness.benchmark.report import BenchmarkReport


def main():
    print("=" * 70)
    print("BTCU Harness Benchmark Suite")
    print("=" * 70)
    print("Comparing BTCU (structured cognitive space) vs baseline (unstructured)")
    print()

    runner = BenchmarkRunner(seed=42)

    # Run all scenarios
    for name in ["investment", "technology", "career"]:
        print(f"Running: {name}...", end=" ", flush=True)
        runner.run_btcu(name)
        runner.run_baseline(name)
        print("done")

    print()
    print(runner.summary())

    # Generate JSON report
    report = BenchmarkReport(runner.results)
    report.save("benchmark_results.json")
    print("\nDetailed results saved to: benchmark_results.json")
    print("Markdown summary saved to: benchmark_report.md")

    # Save markdown report
    with open("benchmark_report.md", "w", encoding="utf-8") as f:
        f.write(report.summary())
        f.write("\n\n## JSON Data\n\n")
        f.write("```json\n")
        f.write(report.to_json())
        f.write("\n```\n")

    print()
    print("Key findings:")
    print("  1. BTCU provides structured cognitive states (0 for baseline)")
    print("  2. BTCU generates third-choice candidates (0 for baseline)")
    print("  3. BTCU tracks trajectory and coverage (0 for baseline)")
    print("  4. BTCU measures consistency across decisions (N/A for baseline)")
    print("  5. Phase 2 would add: token economy (reuse_rate) and pattern learning")


if __name__ == "__main__":
    main()
