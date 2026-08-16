"""Tests for BTCU CLI: command-line interface."""
import json
import os
import sys
import tempfile

import pytest

from btcu_harness.cli import build_parser, main, cmd_init, cmd_explore


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_parser_exists(self):
        parser = build_parser()
        assert parser is not None

    def test_has_all_subcommands(self):
        parser = build_parser()
        # Get subparser actions
        subactions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        commands = list(subactions[0].choices.keys())
        for cmd in ("init", "project", "status", "seasons", "climate", "save", "load", "explore"):
            assert cmd in commands

    def test_no_command_prints_help(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["btcu"])
        ret = main()
        captured = capsys.readouterr()
        assert ret == 0
        assert "usage:" in captured.out.lower() or "btcu" in captured.out.lower()


# ---------------------------------------------------------------------------
# cmd_init
# ---------------------------------------------------------------------------

class TestCmdInit:
    def test_init_agent_domain(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "agent"])
        ret = cmd_init(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "initialized" in out.lower()
        assert "9" in out
        assert os.path.exists(storage)

    def test_init_decision_domain(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "decision"])
        ret = cmd_init(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "initialized" in out.lower()

    def test_init_education_domain(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "education"])
        ret = cmd_init(args)
        assert ret == 0

    def test_init_custom_domain_with_dims(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        dims = "a,b,c,d,e,f,g,h,i"
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "custom", "--dims", dims])
        ret = cmd_init(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "a" in out

    def test_init_custom_without_dims_fails(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "custom"])
        ret = cmd_init(args)
        assert ret == 1
        out = capsys.readouterr().out
        assert "Error" in out

    def test_init_with_mission(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")
        parser = build_parser()
        args = parser.parse_args([
            "--storage", storage, "init",
            "--domain", "agent", "--mission", "save the world",
        ])
        ret = cmd_init(args)
        assert ret == 0


# ---------------------------------------------------------------------------
# cmd_explore
# ---------------------------------------------------------------------------

class TestCmdExplore:
    def test_explore_by_index(self, capsys):
        parser = build_parser()
        args = parser.parse_args(["explore", "--index", "100"])
        ret = cmd_explore(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "State #100" in out
        assert "Polarity" in out
        assert "Neighbors" in out

    def test_explore_by_values(self, capsys):
        parser = build_parser()
        args = parser.parse_args(["explore", "--values", "1,0,-1,1,0,-1,1,0,-1"])
        ret = cmd_explore(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "State #" in out

    def test_explore_no_args_fails(self, capsys):
        parser = build_parser()
        args = parser.parse_args(["explore"])
        ret = cmd_explore(args)
        assert ret == 1
        out = capsys.readouterr().out
        assert "Provide" in out

    def test_explore_all_void(self, capsys):
        """Index 9841 = all-void state."""
        parser = build_parser()
        args = parser.parse_args(["explore", "--index", "9841"])
        ret = cmd_explore(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Void: 9" in out

    def test_explore_all_yang(self, capsys):
        """Index 19682 = all-yang state."""
        parser = build_parser()
        args = parser.parse_args(["explore", "--index", "19682"])
        ret = cmd_explore(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Yang: 9" in out


# ---------------------------------------------------------------------------
# Full pipeline: init -> project -> status -> save -> load
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_init_project_status(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")

        # init
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "agent"])
        assert cmd_init(args) == 0

        # project (school stage without LLM -> ValueError is expected behavior)
        args = parser.parse_args(["--storage", storage, "project", "hello world"])
        with pytest.raises(ValueError, match="LLM callback required"):
            args.func(args)
        capsys.readouterr()  # clear

        # status
        args = parser.parse_args(["--storage", storage, "status"])
        ret = args.func(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "BTCU Agent Status" in out

    def test_save_load_roundtrip(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")

        # init + save
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "agent"])
        cmd_init(args)
        capsys.readouterr()  # clear

        # save
        args = parser.parse_args(["--storage", storage, "save"])
        ret = args.func(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Saved" in out

        # load
        args = parser.parse_args(["--storage", storage, "load"])
        ret = args.func(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Loaded: True" in out

    def test_load_nonexistent_fails(self, capsys, tmp_path):
        storage = str(tmp_path / "nonexistent.json")
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "status"])
        ret = args.func(args)
        assert ret == 1
        out = capsys.readouterr().out
        assert "No saved state" in out


# ---------------------------------------------------------------------------
# seasons & climate
# ---------------------------------------------------------------------------

class TestSeasonsClimate:
    def test_seasons(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")

        # init
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "agent"])
        cmd_init(args)
        capsys.readouterr()

        # seasons (may find 0 or more)
        args = parser.parse_args(["--storage", storage, "seasons"])
        ret = args.func(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Cognitive Seasons" in out

    def test_climate(self, capsys, tmp_path):
        storage = str(tmp_path / "state.json")

        # init
        parser = build_parser()
        args = parser.parse_args(["--storage", storage, "init", "--domain", "agent"])
        cmd_init(args)
        capsys.readouterr()

        # climate report
        args = parser.parse_args(["--storage", storage, "climate"])
        ret = args.func(args)
        assert ret == 0
        out = capsys.readouterr().out
        assert "Climate" in out


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------

class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["btcu"])
        ret = main()
        assert ret == 0

    def test_verbose_flag(self, capsys, tmp_path, monkeypatch):
        storage = str(tmp_path / "state.json")
        monkeypatch.setattr(sys, "argv", [
            "btcu", "--verbose", "--storage", storage, "init", "--domain", "agent",
        ])
        ret = main()
        assert ret == 0

    def test_explore_via_main(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["btcu", "explore", "--index", "0"])
        ret = main()
        assert ret == 0
        out = capsys.readouterr().out
        assert "State #0" in out
