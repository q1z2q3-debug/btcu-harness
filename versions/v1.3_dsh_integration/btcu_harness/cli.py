"""
BTCU Harness CLI: Command-line interface for cognitive operations.

Usage:
    btcu init --domain agent --name "My Agent"
    btcu project "Should we focus on innovation?"
    btcu status
    btcu seasons
    btcu climate
    btcu save
    btcu load

The CLI provides a human-friendly interface to the BTCU Agent,
supporting interactive sessions and batch processing.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .agent import BTCUAgent
from .core.state import CognitiveState
from .logging_config import setup_logging, get_logger

logger = get_logger("btcu_harness.cli")


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new BTCU project."""
    agent = BTCUAgent(
        growth_stage="school",
        storage_path=args.storage or "btcu_state.json",
    )

    # Default dimensions or custom
    if args.domain == "agent":
        dim_labels = [
            "任务理解", "工具匹配", "风险评估", "用户意图",
            "资源消耗", "创新程度", "可解释性", "时效性", "长期价值",
        ]
    elif args.domain == "decision":
        dim_labels = [
            "紧迫性", "重要性", "资源可用", "风险水平",
            "团队支持", "技术可行", "战略对齐", "时间约束", "长期影响",
        ]
    elif args.domain == "education":
        dim_labels = [
            "知识掌握", "学习动力", "认知负荷", "实践能力",
            "创新思维", "协作能力", "反思能力", "学习策略", "成长心态",
        ]
    else:
        if not args.dims:
            print("Error: --dims required for custom domain")
            return 1
        dim_labels = args.dims.split(",")

    agent.init_project(domain=args.domain, dim_labels=dim_labels)

    # Set mission if provided
    if args.mission:
        mission_vals = [0] * 9  # default void
        agent.set_self_level(
            name="mission",
            description=args.mission,
            state=CognitiveState.from_values(mission_vals),
            weight=1.0,
            stability=0.95,
        )

    agent.save()
    print(f"Project initialized: domain={args.domain}, dims={len(dim_labels)}")
    print(f"  Dimensions: {dim_labels}")
    print(f"  Storage: {args.storage or 'btcu_state.json'}")
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    """Project an input onto the cognitive space."""
    agent = _load_agent(args)
    if agent is None:
        return 1

    response = agent.process(args.input)
    print(response.summary())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show agent status."""
    agent = _load_agent(args)
    if agent is None:
        return 1
    print(agent.status())
    return 0


def cmd_seasons(args: argparse.Namespace) -> int:
    """Discover cognitive seasons."""
    agent = _load_agent(args)
    if agent is None:
        return 1
    seasons = agent.discover_seasons()
    print(f"=== Cognitive Seasons ({len(seasons)} found) ===")
    for s in seasons:
        print(f"  [{s.season_type}] {s.description}")
    return 0


def cmd_climate(args: argparse.Namespace) -> int:
    """Generate climate report."""
    agent = _load_agent(args)
    if agent is None:
        return 1
    print(agent.climate_report())
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    """Save cognitive state."""
    agent = _load_agent(args)
    if agent is None:
        return 1
    path = agent.save()
    if path:
        print(f"Saved to: {path}")
        return 0
    print("No storage path configured")
    return 1


def cmd_load(args: argparse.Namespace) -> int:
    """Load cognitive state."""
    agent = _load_agent(args)
    if agent is None:
        return 1
    loaded = agent.load()
    print(f"Loaded: {loaded}")
    if loaded:
        print(agent.status())
    return 0


def cmd_explore(args: argparse.Namespace) -> int:
    """Explore the cognitive space - show info about a state."""
    if args.index is not None:
        state = CognitiveState.from_index(args.index)
    elif args.values:
        vals = [int(v) for v in args.values.split(",")]
        state = CognitiveState.from_values(vals)
    else:
        print("Provide --index or --values")
        return 1

    print(f"State #{state.index}")
    print(f"  Values: {[state[i].value for i in range(9)]}")
    print(f"  Polarity: {state.polarity:+d}")
    print(f"  Yang: {state.yang_count} | Void: {state.void_count} | Yin: {state.yin_count}")
    print(f"  Opposite: #{state.opposite().index}")
    print(f"  Distance to void: {state.distance(CognitiveState.all_void())}")

    neighbors = []
    for i in range(9):
        val = state[i].value
        if val < 1:
            neighbors.append(f"d{i}:+1->{state.with_dimension(i, val+1).index}")
        if val > -1:
            neighbors.append(f"d{i}:-1->{state.with_dimension(i, val-1).index}")
    print(f"  Neighbors ({len(neighbors)}): {', '.join(neighbors[:6])}...")
    return 0


def _load_agent(args: argparse.Namespace) -> Optional[BTCUAgent]:
    """Load agent from storage."""
    storage = getattr(args, "storage", None) or "btcu_state.json"
    agent = BTCUAgent(storage_path=storage)
    loaded = agent.load()
    if not loaded:
        print(f"No saved state found at {storage}. Run 'btcu init' first.")
        return None
    return agent


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="btcu",
        description="BTCU Harness - Balanced Ternary Cognitive Unit CLI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--storage",
        default=None,
        help="Storage file path (default: btcu_state.json)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new project")
    p_init.add_argument(
        "--domain",
        default="agent",
        choices=["agent", "decision", "education", "custom"],
        help="Domain template (default: agent)",
    )
    p_init.add_argument("--dims", help="Comma-separated dimension labels (custom domain)")
    p_init.add_argument("--mission", help="Mission statement")
    p_init.add_argument("--name", help="Project name")
    p_init.set_defaults(func=cmd_init)

    # project
    p_project = subparsers.add_parser("project", help="Project an input")
    p_project.add_argument("input", help="Input text to project")
    p_project.set_defaults(func=cmd_project)

    # status
    p_status = subparsers.add_parser("status", help="Show agent status")
    p_status.set_defaults(func=cmd_status)

    # seasons
    p_seasons = subparsers.add_parser("seasons", help="Discover cognitive seasons")
    p_seasons.set_defaults(func=cmd_seasons)

    # climate
    p_climate = subparsers.add_parser("climate", help="Generate climate report")
    p_climate.set_defaults(func=cmd_climate)

    # save
    p_save = subparsers.add_parser("save", help="Save cognitive state")
    p_save.set_defaults(func=cmd_save)

    # load
    p_load = subparsers.add_parser("load", help="Load cognitive state")
    p_load.set_defaults(func=cmd_load)

    # explore
    p_explore = subparsers.add_parser("explore", help="Explore a cognitive state")
    p_explore.add_argument("--index", type=int, help="State index (0-19682)")
    p_explore.add_argument("--values", help="Comma-separated values (e.g. 1,0,-1,1,0,0,-1,1,-1)")
    p_explore.set_defaults(func=cmd_explore)

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        setup_logging(level="DEBUG")
    else:
        setup_logging(level="WARNING")

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
