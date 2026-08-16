"""
Token Economy Simulation: Demonstrate LLM cost reduction as BTCU learns patterns.

Run:
    python examples/token_economy_demo.py

This simulates 1000 cognitive inputs across three growth stages,
showing how pattern learning progressively reduces LLM dependency.
"""

from btcu_harness.benchmark.token_economy import TokenEconomySimulator


def main():
    print("BTCU Token Economy Simulation")
    print("Simulating 1000 inputs across school→internalize→graduate stages...")
    print("This may take a moment...\n")

    sim = TokenEconomySimulator(total_steps=1000, snapshot_interval=50)
    sim.run()

    print(sim.summary())

    # Save results
    sim.save_json("token_economy_results.json")
    print("\nResults saved to: token_economy_results.json")

    with open("token_economy_report.md", "w", encoding="utf-8") as f:
        f.write("# BTCU Token Economy Report\n\n")
        f.write("## Simulation Parameters\n\n")
        f.write(f"- Total inputs: {sim.result.total_steps}\n")
        f.write("- Stage split: 20% school / 40% internalize / 40% graduate\n")
        f.write("- Snapshot interval: every 50 steps\n\n")
        f.write("## Results\n\n")
        f.write(f"- Final LLM calls: {sim.result.final_llm_calls}\n")
        f.write(f"- Final patterns learned: {sim.result.final_patterns}\n")
        f.write(f"- Final reuse rate: {sim.result.final_reuse_rate:.1%}\n")
        f.write(f"- Final unique states: {sim.result.final_unique_states}\n\n")
        f.write("## Key Finding\n\n")
        f.write("As the agent progresses from school to graduate stage,\n")
        f.write("pattern learning reduces LLM dependency.\n")
        f.write("In a production system with real LLM, the savings would be:\n\n")
        f.write("```\n")
        f.write("school:     C ~ N        (every input needs LLM)\n")
        f.write("internalize: C ~ N * (1 - r)  (r = reuse_rate)\n")
        f.write("graduate:    C ~ N * u      (u = unknown_rate → 0)\n")
        f.write("```\n")

    print("Report saved to: token_economy_report.md")
    print("\nGenerate charts with: python examples/token_economy_charts.py")


if __name__ == "__main__":
    main()
