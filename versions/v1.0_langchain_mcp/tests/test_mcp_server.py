"""
Integration tests for the BTCU MCP Server.

Tests the JSON-RPC 2.0 protocol over stdio, covering:
  - Initialization handshake
  - Tools list/call
  - Resources list/read
  - Prompts list/get
  - Error handling
  - Session persistence
  - Rule-based projection

Run with:
    pytest tests/test_mcp_server.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import uuid
from io import StringIO
from typing import Any, Dict, List, Optional

import pytest

# Ensure btcu_harness is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcu_harness.mcp.server import (
    BTCUMCPServer,
    ERR_INVALID_PARAMS,
    ERR_INVALID_REQUEST,
    ERR_METHOD_NOT_FOUND,
    ERR_PARSE_ERROR,
    make_error,
    make_response,
    rule_based_project,
)
from btcu_harness.core.state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    """Create a fresh server instance (no MongoDB)."""
    return BTCUMCPServer(mongo_uri=None, db_name=None)


@pytest.fixture
def temp_mongo():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# ---------------------------------------------------------------------------
# JSON-RPC helper tests
# ---------------------------------------------------------------------------

class TestJSONRPCHelpers:
    def test_make_response_with_result(self):
        resp = make_response(1, result={"foo": "bar"})
        assert resp == {"jsonrpc": "2.0", "id": 1, "result": {"foo": "bar"}}

    def test_make_response_without_result(self):
        resp = make_response(2)
        assert resp == {"jsonrpc": "2.0", "id": 2, "result": {}}

    def test_make_error(self):
        resp = make_error(3, -32600, "Invalid Request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 3
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "Invalid Request"


# ---------------------------------------------------------------------------
# Server dispatch tests
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_initialize_returns_capabilities(self, server):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = server.dispatch(msg)

        assert resp is not None
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp

        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "capabilities" in result
        assert "tools" in result["capabilities"]
        assert "resources" in result["capabilities"]
        assert "prompts" in result["capabilities"]
        assert result["serverInfo"]["name"] == "btcu-harness-mcp"
        assert "version" in result["serverInfo"]

    def test_initialize_stores_client_capabilities(self, server):
        caps = {"experimental": {"foo": True}}
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": caps},
        }
        server.dispatch(msg)
        assert server._client_capabilities == caps


class TestToolsList:
    def test_tools_list_returns_tools(self, server):
        msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        tools = resp["result"]["tools"]
        assert len(tools) == 4

        names = {t["name"] for t in tools}
        assert names == {
            "cognitive_project",
            "analyze_consistency",
            "suggest_tools",
            "cognitive_compare",
        }

        # Verify schemas exist
        for tool in tools:
            assert "inputSchema" in tool
            assert "description" in tool


class TestToolsCall:
    def test_cognitive_project_basic(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "This is a positive and helpful message",
                    "session_id": "test_session_1",
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        content = resp["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"

        result = json.loads(content[0]["text"])
        assert "state" in result
        assert "index" in result["state"]
        assert "values" in result["state"]
        assert len(result["state"]["values"]) == NUM_DIMENSIONS
        assert result["session_id"] == "test_session_1"
        assert "confidence" in result
        assert result["source"] == "rule_based"

    def test_cognitive_project_empty_input_returns_void(self, server):
        """Empty input produces a void state with low confidence."""
        msg = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {"input": "", "session_id": "test"},
            },
        }
        resp = server.dispatch(msg)

        # Empty string input produces void state via rule-based projection
        assert resp is not None
        assert "result" in resp
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["source"] == "rule_based"
        assert result["state"]["index"] == 9841  # ALL_VOID
        assert result["confidence"] == 0.3

    def test_cognitive_project_missing_input(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {"session_id": "test"},
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == -32603  # Internal error (ValueError)

    def test_cognitive_compare_valid(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [1, 1, 1, 1, 1, 1, 1, 1, 1],
                    "state_b": [-1, -1, -1, -1, -1, -1, -1, -1, -1],
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        result = json.loads(resp["result"]["content"][0]["text"])

        assert result["distance"] == 18
        assert result["is_opposite"] is True
        assert result["differing_count"] == 9
        assert result["path_length"] == 18  # 9 dims * 2 steps each (1->0->-1)
        assert result["max_possible_distance"] == 18
        assert "interpretation" in result
        assert "dimension_comparison" in result
        assert len(result["dimension_comparison"]) == NUM_DIMENSIONS

    def test_cognitive_compare_same_state(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [0, 0, 0, 0, 0, 0, 0, 0, 0],
                    "state_b": [0, 0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
        }
        resp = server.dispatch(msg)

        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["distance"] == 0
        assert result["is_opposite"] is False
        assert result["differing_count"] == 0
        assert result["path_length"] == 0
        assert result["is_opposite"] is False

    def test_cognitive_compare_invalid_dimensions(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [1, 0],
                    "state_b": [0, 0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
        }
        resp = server.dispatch(msg)

        assert "error" in resp
        assert resp["error"]["code"] == -32603

    def test_analyze_consistency_with_sequence(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "analyze_consistency",
                "arguments": {
                    "state_sequence": [
                        [0, 0, 0, 0, 0, 0, 0, 0, 0],
                        [1, 0, 0, 0, 0, 0, 0, 0, 0],
                        [1, 1, 0, 0, 0, 0, 0, 0, 0],
                        [1, 1, 1, 0, 0, 0, 0, 0, 0],
                    ],
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        result = json.loads(resp["result"]["content"][0]["text"])

        assert "consistency_score" in result
        assert "average_distance" in result
        assert "velocity" in result
        assert "drift" in result
        assert "sequence_length" in result
        assert result["sequence_length"] == 4
        assert result["drift"] > 0

    def test_analyze_consistency_empty_sequence(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "analyze_consistency",
                "arguments": {},
            },
        }
        resp = server.dispatch(msg)

        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["sequence_length"] == 0
        assert result["consistency_score"] == 1.0
        assert "note" in result

    def test_suggest_tools_with_state(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "suggest_tools",
                "arguments": {
                    "state_values": [1, 1, 1, 1, 1, 1, 1, 1, 1],
                    "session_id": "test_suggest",
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        result = json.loads(resp["result"]["content"][0]["text"])

        assert "state" in result
        assert "suggestions" in result
        assert isinstance(result["suggestions"], list)
        assert len(result["suggestions"]) > 0

    def test_suggest_tools_without_state(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "suggest_tools",
                "arguments": {"session_id": "test_suggest_empty"},
            },
        }
        resp = server.dispatch(msg)

        result = json.loads(resp["result"]["content"][0]["text"])
        assert "state" in result
        assert result["state"]["index"] == 9841  # ALL_VOID

    def test_unknown_tool_returns_error(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "nonexistent_tool",
                "arguments": {},
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND
        assert "nonexistent_tool" in resp["error"]["message"]


class TestResources:
    def test_resources_list(self, server):
        msg = {"jsonrpc": "2.0", "id": 14, "method": "resources/list", "params": {}}
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        resources = resp["result"]["resources"]
        assert len(resources) == 3

        uris = {r["uri"] for r in resources}
        assert "cognitive://dimensions" in uris
        assert any("trajectory" in uri for uri in uris)
        assert any("patterns" in uri for uri in uris)

    def test_resources_read_dimensions(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "resources/read",
            "params": {"uri": "cognitive://dimensions"},
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        contents = resp["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["uri"] == "cognitive://dimensions"
        assert contents[0]["mimeType"] == "application/json"

        data = json.loads(contents[0]["text"])
        assert len(data) == NUM_DIMENSIONS
        assert data[0]["name"] == "stance"
        assert "description" in data[0]
        assert "values" in data[0]

    def test_resources_read_trajectory_empty(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/test_empty/trajectory"},
        }
        resp = server.dispatch(msg)

        assert resp is not None
        contents = resp["result"]["contents"]
        data = json.loads(contents[0]["text"])
        assert data["session_id"] == "test_empty"
        assert data["length"] == 0

    def test_resources_read_patterns_empty(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 17,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/test_empty/patterns"},
        }
        resp = server.dispatch(msg)

        assert resp is not None
        contents = resp["result"]["contents"]
        data = json.loads(contents[0]["text"])
        assert data["session_id"] == "test_empty"
        assert data["pattern_count"] == 0

    def test_resources_read_unknown_uri(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 18,
            "method": "resources/read",
            "params": {"uri": "cognitive://unknown"},
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


class TestPrompts:
    def test_prompts_list(self, server):
        msg = {"jsonrpc": "2.0", "id": 19, "method": "prompts/list", "params": {}}
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        prompts = resp["result"]["prompts"]
        assert len(prompts) == 1
        assert prompts[0]["name"] == "cognitive_context"

    def test_prompts_get_valid(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "prompts/get",
            "params": {
                "name": "cognitive_context",
                "arguments": {
                    "state_values": [1, 0, -1, 1, 0, 0, -1, 1, 0],
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "result" in resp
        result = resp["result"]
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "system"

        content = result["messages"][0]["content"]
        assert content["type"] == "text"
        text = content["text"]
        assert "BTCU Cognitive State Context" in text
        assert "stance" in text
        assert "intensity" in text

    def test_prompts_get_invalid_dimensions(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "prompts/get",
            "params": {
                "name": "cognitive_context",
                "arguments": {
                    "state_values": [1, 0],  # Too short
                },
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_prompts_get_unknown_prompt(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "prompts/get",
            "params": {
                "name": "unknown_prompt",
                "arguments": {},
            },
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_INVALID_PARAMS


class TestNotifications:
    def test_notifications_initialized(self, server):
        msg = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        resp = server.dispatch(msg)

        # Notifications have no response
        assert resp is None


class TestErrorHandling:
    def test_invalid_json_rpc_version(self, server):
        msg = {"jsonrpc": "1.0", "id": 23, "method": "tools/list", "params": {}}
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_INVALID_REQUEST

    def test_unknown_method(self, server):
        msg = {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "unknown/method",
            "params": {},
        }
        resp = server.dispatch(msg)

        assert resp is not None
        assert "error" in resp
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND

    def test_notification_unknown_method_no_response(self, server):
        msg = {
            "jsonrpc": "2.0",
            "method": "unknown/notification",
            "params": {},
        }
        resp = server.dispatch(msg)

        # Notifications don't return errors either
        assert resp is None


# ---------------------------------------------------------------------------
# Integration tests: full stdio loop simulation
# ---------------------------------------------------------------------------

class TestStdioLoop:
    def test_full_server_loop(self):
        """Test the complete read-dispatch-write cycle via StringIO."""
        server = BTCUMCPServer(mongo_uri=None, db_name=None)

        # Prepare input lines
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "cognitive_project",
                    "arguments": {"input": "Test message", "session_id": "loop_test"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "cognitive://dimensions"},
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "prompts/get",
                "params": {
                    "name": "cognitive_context",
                    "arguments": {"state_values": [0] * NUM_DIMENSIONS},
                },
            },
        ]

        input_text = "\n".join(json.dumps(req) for req in requests) + "\n"

        old_stdin = sys.stdin
        old_stdout = sys.stdout

        try:
            sys.stdin = StringIO(input_text)
            sys.stdout = StringIO()

            # Run server (it reads until EOF)
            server.run()

            # Read output
            sys.stdout.seek(0)
            output_lines = sys.stdout.read().strip().split("\n")

            # Should have 5 responses (one per request)
            assert len(output_lines) == 5

            # Verify each response
            for i, line in enumerate(output_lines):
                resp = json.loads(line)
                assert resp["jsonrpc"] == "2.0"
                assert resp["id"] == i + 1
                assert "result" in resp
                assert "error" not in resp

            # Verify specific results
            resp3 = json.loads(output_lines[2])
            result3 = json.loads(resp3["result"]["content"][0]["text"])
            assert result3["session_id"] == "loop_test"
            assert "state" in result3

            resp5 = json.loads(output_lines[4])
            assert "messages" in resp5["result"]

        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_parse_error_handling(self):
        """Test that invalid JSON produces parse error responses."""
        server = BTCUMCPServer(mongo_uri=None, db_name=None)

        input_text = "not valid json\n"

        old_stdin = sys.stdin
        old_stdout = sys.stdout

        try:
            sys.stdin = StringIO(input_text)
            sys.stdout = StringIO()

            server.run()

            sys.stdout.seek(0)
            output = sys.stdout.read().strip()
            resp = json.loads(output)

            assert resp["jsonrpc"] == "2.0"
            assert "error" in resp
            assert resp["error"]["code"] == ERR_PARSE_ERROR

        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout


# ---------------------------------------------------------------------------
# Rule-based projection tests
# ---------------------------------------------------------------------------

class TestRuleBasedProjection:
    def test_positive_text(self):
        values, assessments, confidence = rule_based_project(
            "This is excellent and wonderful! We should build great things together."
        )
        assert len(values) == NUM_DIMENSIONS
        assert all(v in (-1, 0, 1) for v in values)
        assert confidence >= 0.3
        # Check that some dimension assessments exist
        assert any("dim_" in k for k in assessments.keys())

    def test_negative_text(self):
        values, assessments, confidence = rule_based_project(
            "This is terrible and bad. We failed and destroyed everything."
        )
        assert len(values) == NUM_DIMENSIONS
        assert confidence >= 0.3

    def test_neutral_text(self):
        values, assessments, confidence = rule_based_project(
            "The object is located on the table."
        )
        assert len(values) == NUM_DIMENSIONS
        # Neutral text may have low confidence due to few keyword matches
        assert confidence >= 0.3

    def test_empty_text(self):
        values, assessments, confidence = rule_based_project("")
        assert values == [0] * NUM_DIMENSIONS
        assert confidence == 0.3

    def test_question_text(self):
        values, assessments, confidence = rule_based_project(
            "How should we approach this problem? What is the best solution?"
        )
        assert len(values) == NUM_DIMENSIONS
        # Should detect inquiry mode
        assert confidence >= 0.3


# ---------------------------------------------------------------------------
# Session state tests
# ---------------------------------------------------------------------------

class TestSessionState:
    def test_session_initialization(self, server):
        # First tool call should auto-initialize the session
        msg = {
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "Initialize session test",
                    "session_id": "sess_init_test",
                    "domain": "agent",
                },
            },
        }
        resp = server.dispatch(msg)
        assert "result" in resp

        # Now trajectory should have a point
        msg2 = {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/sess_init_test/trajectory"},
        }
        resp2 = server.dispatch(msg2)
        contents = resp2["result"]["contents"]
        data = json.loads(contents[0]["text"])
        assert data["length"] == 1

    def test_multiple_sessions_isolated(self, server):
        # Project in session A
        msg_a = {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "Session A input",
                    "session_id": "sess_a",
                },
            },
        }
        server.dispatch(msg_a)

        # Project in session B
        msg_b = {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "Session B input",
                    "session_id": "sess_b",
                },
            },
        }
        server.dispatch(msg_b)

        # Check A has 1 point
        msg_read_a = {
            "jsonrpc": "2.0",
            "id": 34,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/sess_a/trajectory"},
        }
        resp_a = server.dispatch(msg_read_a)
        data_a = json.loads(resp_a["result"]["contents"][0]["text"])
        assert data_a["length"] == 1

        # Check B has 1 point
        msg_read_b = {
            "jsonrpc": "2.0",
            "id": 35,
            "method": "resources/read",
            "params": {"uri": "cognitive://sessions/sess_b/trajectory"},
        }
        resp_b = server.dispatch(msg_read_b)
        data_b = json.loads(resp_b["result"]["contents"][0]["text"])
        assert data_b["length"] == 1


# ---------------------------------------------------------------------------
# Server info tests
# ---------------------------------------------------------------------------

class TestServerMetadata:
    def test_server_version(self, server):
        assert server.SERVER_VERSION == "1.1.0"
        assert server.SERVER_NAME == "btcu-harness-mcp"
        assert server.PROTOCOL_VERSION == "2024-11-05"

    def test_tools_have_descriptions(self, server):
        for tool in server.tools:
            assert tool["description"]
            assert len(tool["description"]) > 10

    def test_resources_have_mime_types(self, server):
        for resource in server.resources:
            assert resource["mimeType"] == "application/json"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_cognitive_compare_adjacent_states(self, server):
        """Two states differing by one dimension."""
        msg = {
            "jsonrpc": "2.0",
            "id": 40,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [0, 0, 0, 0, 0, 0, 0, 0, 0],
                    "state_b": [1, 0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
        }
        resp = server.dispatch(msg)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["distance"] == 1
        assert result["differing_count"] == 1
        assert result["path_length"] == 1

    def test_cognitive_project_long_text(self, server):
        """Test with a very long input text."""
        long_text = "positive " * 500
        msg = {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": long_text,
                    "session_id": "long_text_test",
                },
            },
        }
        resp = server.dispatch(msg)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert "state" in result
        assert result["confidence"] >= 0.3

    def test_unicode_input(self, server):
        """Test with unicode characters in input."""
        msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "tools/call",
            "params": {
                "name": "cognitive_project",
                "arguments": {
                    "input": "Cognitive state: positive! Good morning! 今日は良い日ですね。",
                    "session_id": "unicode_test",
                },
            },
        }
        resp = server.dispatch(msg)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert "state" in result

    def test_invalid_trit_values(self, server):
        """Test with values outside {-1, 0, 1}."""
        msg = {
            "jsonrpc": "2.0",
            "id": 43,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [2, 3, -2, 0, 0, 0, 0, 0, 0],  # Invalid
                    "state_b": [0, 0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
        }
        resp = server.dispatch(msg)
        assert "error" in resp

    def test_special_state_indices(self, server):
        """Test with ALL_YIN and ALL_YANG extreme states."""
        msg = {
            "jsonrpc": "2.0",
            "id": 44,
            "method": "tools/call",
            "params": {
                "name": "cognitive_compare",
                "arguments": {
                    "state_a": [-1] * NUM_DIMENSIONS,  # ALL_YIN
                    "state_b": [1] * NUM_DIMENSIONS,   # ALL_YANG
                },
            },
        }
        resp = server.dispatch(msg)
        result = json.loads(resp["result"]["content"][0]["text"])
        assert result["state_a"]["index"] == 0
        assert result["state_b"]["index"] == SPACE_SIZE - 1
        assert result["is_opposite"] is True
        assert result["distance"] == 18

    def test_empty_line_ignored(self):
        """Empty lines in stdin should be ignored, not crash."""
        server = BTCUMCPServer(mongo_uri=None, db_name=None)

        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        input_text = "\n\n" + json.dumps(req) + "\n\n"

        old_stdin = sys.stdin
        old_stdout = sys.stdout

        try:
            sys.stdin = StringIO(input_text)
            sys.stdout = StringIO()

            server.run()

            sys.stdout.seek(0)
            output_lines = sys.stdout.read().strip().split("\n")
            assert len(output_lines) == 1
            resp = json.loads(output_lines[0])
            assert resp["id"] == 1
            assert "tools" in resp["result"]

        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout
