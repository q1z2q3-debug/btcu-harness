"""Generate visualization charts from token economy simulation results.

Usage:
    python examples/token_economy_charts.py

Reads token_economy_results.json and produces:
    docs/images/token_economy_llm_calls.png
    docs/images/token_economy_reuse_rate.png
"""

import json

with open("token_economy_results.json") as f:
    data = json.load(f)

snapshots = data["snapshots"]
steps = [s["step"] for s in snapshots]
llm_calls = [s["llm_calls"] for s in snapshots]
reuse_rates = [s["reuse_rate"] for s in snapshots]
pattern_counts = [s["pattern_count"] for s in snapshots]

import matplotlib.pyplot as plt
import numpy as np

# Chart 1: LLM calls over time
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

# Left: Cumulative LLM calls
ax1.plot(steps, llm_calls, linewidth=2, color="#E53935", marker="o", markersize=4)
ax1.set_xlabel("Input Step")
ax1.set_ylabel("Cumulative LLM Calls")
ax1.set_title("LLM Call Accumulation")
ax1.grid(alpha=0.3)

# Add stage annotations
ax1.axvline(x=200, color="gray", linestyle="--", alpha=0.5, label="school→internalize")
ax1.axvline(x=600, color="gray", linestyle="--", alpha=0.5, label="internalize→graduate")
ax1.text(100, max(llm_calls) * 0.9, "school", fontsize=10, color="gray", ha="center")
ax1.text(400, max(llm_calls) * 0.9, "internalize", fontsize=10, color="gray", ha="center")
ax1.text(800, max(llm_calls) * 0.9, "graduate", fontsize=10, color="gray", ha="center")

# Right: Reuse rate over time
ax2.plot(steps, [r * 100 for r in reuse_rates], linewidth=2, color="#43A047", marker="s", markersize=4)
ax2.set_xlabel("Input Step")
ax2.set_ylabel("Reuse Rate (%)")
ax2.set_title("Pattern Reuse Rate Growth")
ax2.set_ylim(0, 100)
ax2.grid(alpha=0.3)

ax2.axvline(x=200, color="gray", linestyle="--", alpha=0.5)
ax2.axvline(x=600, color="gray", linestyle="--", alpha=0.5)
ax2.text(100, 95, "school", fontsize=10, color="gray", ha="center")
ax2.text(400, 95, "internalize", fontsize=10, color="gray", ha="center")
ax2.text(800, 95, "graduate", fontsize=10, color="gray", ha="center")

plt.tight_layout()
plt.savefig("docs/images/token_economy.png", dpi=150, bbox_inches="tight")
print("Chart saved to: docs/images/token_economy.png")

# Chart 2: Per-batch LLM calls (shows the drop)
fig, ax = plt.subplots(figsize=(10, 5))

batch_calls = [s["llm_calls_this_batch"] for s in snapshots]
ax.bar(steps, batch_calls, width=40, color="#FB8C00", edgecolor="white", linewidth=0.5)
ax.set_xlabel("Input Step")
ax.set_ylabel("LLM Calls per 50-Step Batch")
ax.set_title("LLM Call Reduction Per Batch")
ax.axvline(x=200, color="gray", linestyle="--", alpha=0.5)
ax.axvline(x=600, color="gray", linestyle="--", alpha=0.5)
ax.text(100, max(batch_calls) * 0.9, "school", fontsize=10, color="gray", ha="center")
ax.text(400, max(batch_calls) * 0.9, "internalize", fontsize=10, color="gray", ha="center")
ax.text(800, max(batch_calls) * 0.9, "graduate", fontsize=10, color="gray", ha="center")
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig("docs/images/token_economy_batch.png", dpi=150, bbox_inches="tight")
print("Chart saved to: docs/images/token_economy_batch.png")
