#!/usr/bin/env python3
"""
BTCU MCP Server Demo Script.

Demonstrates how to interact with the BTCU MCP Server programmatically
via JSON-RPC 2.0 over stdio. This simulates what an MCP client (like
Claude Desktop or Cursor) would do.

Usage:
    python examples/mcp_demo.py

Prerequisites:
    pip install -e .  # Install btcu-harness
    # The MCP server runs in the same process for demo purposes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, Optional


def send_request(proc: subprocess.Popen, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Send a JSON-RPC request to the MCP server process and read the response."""
    line = json.dumps(request)
    print(f"--> {line}")
    proc.stdin.write(line + "\n")  # type: ignore[union-attr]
    proc.stdin.flush()  # type: ignore[union-attr]

    response_line = proc.stdout.readline().strip()  # type: ignore[union-attr]
    print(f"<-- {response_line}")
    return json.loads(response_line) if response_line else None


def main():
    """Run a demonstration of all MCP server capabilities."""
    print("=" * 70)
    print("BTCU Harness MCP Server Demo")
    print("=" * 70)
    print()

    # Start the MCP server as a subprocess
    cmd = [sys.executable, "-m", "btcu_harness.mcp.server"]
    print(f"Starting MCP server: {' '.join(cmd)}")
    print("-" * 70)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # 1. Initialize
        print("\n[1] Initialize handshake")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        })
        if resp:
            result = resp.get("result", {})
            print(f"Server: {result.get('serverInfo', {})}")
            print(f"Protocol: {result.get('protocolVersion')}")
            print(f"Capabilities: {list(result.get('capabilities', {}).keys())}")

        # 2. Send initialized notification
        print("\n[2] Send initialized notification")
        print("-" * 40)
        proc.stdin.write(json.dumps({  # type: ignore[union-attr]
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }) + "\n")
        proc.stdin.flush()  # type: ignore[union-attr]
        print("(no response expected for notifications)")

        # 3. List tools
        print("\n[3] List available tools")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })
        if resp:
            tools = resp.get("result", {}).get("tools", [])
            for tool in tools:
                print(f"  - {tool['name']}: {tool['description'][:60]}...")

        # 4. Call cognitive_project
        print("\n[4] Tool call: cognitive_project")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "We need to build a scalable solution that helps the team collaborate better and delivers value quickly.",
                    "session_id": "demo_session",
                    "domain": "agent",
                },
            },
        })
        if resp:
            content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
            result = json.loads(content)
            state = result.get("state", {})
            print(f"  State index: #{state.get('index')}")
            print(f"  Values: {state.get('values')}")
            print(f"  Polarity: {state.get('polarity')}")
            print(f"  Confidence: {result.get('confidence'):.2%}")
            print(f"  Source: {result.get('source')}")
            print(f"  Trajectory length: {result.get('trajectory_length')}")

        # 5. Call cognitive_compare
        print("\n[5] Tool call: cognitive_compare")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [1, 1, 1, 1, 1, 1, 1, 1, 1],   # All YANG
                    "state_b": [-1, -1, -1, -1, -1, -1, -1, -1, -1],  # All YIN
                },
            },
        })
        if resp:
            content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
            result = json.loads(content)
            print(f"  Distance: {result.get('distance')}/18")
            print(f"  Is opposite: {result.get('is_opposite')}")
            print(f"  Path length: {result.get('path_length')} steps")
            print(f"  Differing dimensions: {result.get('differing_count')}")
            print(f"  Interpretation: {result.get('interpretation')}")

        # 6. Call analyze_consistency
        print("\n[6] Tool call: analyze_consistency")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "analyze_consistency",
                "arguments": {
                    "state_sequence": [
                        [0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [1, 0, 0, 0, 0, 0, 0, 0, 0],
                        [1, 1, 0, 0, 0, 0, 0, 0, 0],
                        [1, 1, 1, 0, 0, 0, 0, 0, 0],
                        [1, 1, 1, 1, 0, 0, 0, 0, 0],
                    ],
                },
            },
        })
        if resp:
            content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
            result = json.loads(content)
            print(f"  Consistency score: {result.get('consistency_score'):.2%}")
            print(f"  Average distance: {result.get('average_distance')}")
            print(f"  Velocity: {result.get('velocity')}")
            print(f"  Drift: {result.get('drift')}")
            print(f"  Cycles detected: {len(result.get('cycles_detected', []))}")

        # 7. Call suggest_tools
        print("\n[7] Tool call: suggest_tools")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "suggest_tools",
                "arguments": {
                    "state_values": [1, 1, 1, 1, 1, 1, 1, 1, 1],
                    "session_id": "demo_session",
                },
            },
        })
        if resp:
            content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
            result = json.loads(content)
            suggestions = result.get("suggestions", [])
            print(f"  Suggestions ({len(suggestions)}):")
            for s in suggestions[:3]:
                print(f"    - {s}")

        # 8. List resources
        print("\n[8] List available resources")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/list",
            "params": {},
        })
        if resp:
            resources = resp.get("result", {}).get("resources", [])
            for res in resources:
                print(f"  - {res['uri']}: {res['description'][:50]}...")

        # 9. Read dimensions resource
        print("\n[9] Read resource: cognitive://dimensions")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "resources/read",
            "params": {"uri": "cognitive://dimensions"},
        })
        if resp:
            contents = resp.get("result", {}).get("contents", [{}])[0]
            data = json.loads(contents.get("text", "{}"))
            for dim in data:
                print(f"  - {dim['name']}: {dim['description'][:50]}...")

        # 10. Read trajectory resource
        print("\n[10] Read resource: session trajectory")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/demo_session/trajectory"},
        })
        if resp:
            contents = resp.get("result", {}).get("contents", [{}])[0]
            data = json.loads(contents.get("text", "{}"))
            print(f"  Session: {data.get('session_id')}")
            print(f"  Trajectory length: {data.get('length')}")
            print(f"  Unique states: {data.get('unique_states')}")
            print(f"  Coverage: {data.get('coverage', 0):.4%}")

        # 11. List prompts
        print("\n[11] List available prompts")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "prompts/list",
            "params": {},
        })
        if resp:
            prompts = resp.get("result", {}).get("prompts", [])
            for prompt in prompts:
                print(f"  - {prompt['name']}: {prompt['description'][:50]}...")

        # 12. Get cognitive_context prompt
        print("\n[12] Get prompt: cognitive_context")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "prompts/get",
            "params": {
                "name": "cognitive_context",
                "arguments": {
                    "state_values": [1, 0, -1, 1, 0, 0, -1, 1, 0],
                    "session_id": "demo_session",
                },
            },
        })
        if resp:
            result = resp.get("result", {})
            messages = result.get("messages", [])
            if messages:
                content = messages[0].get("content", {}).get("text", "")
                # Show first few lines
                lines = content.split("\n")[:8]
                for line in lines:
                    print(f"  {line}")
                print("  ...")

        # 13. Error handling demo
        print("\n[13] Error handling demo: unknown tool")
        print("-" * 40)
        resp = send_request(proc, {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        })
        if resp:
            error = resp.get("error", {})
            print(f"  Error code: {error.get('code')}")
            print(f"  Error message: {error.get('message')}")

        print("\n" + "=" * 70)
        print("Demo complete!")
        print("=" * 70)

    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
