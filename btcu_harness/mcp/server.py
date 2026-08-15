"""
BTCU MCP Server: Model Context Protocol over stdio JSON-RPC 2.0.

Exposes BTCU Harness cognitive architecture through the MCP protocol,
enabling any MCP client (Claude Desktop, Cursor, etc.) to access:
  - Cognitive projection tools (project text to 9D ternary state)
  - Decision consistency analysis
  - Cognitive state comparison
  - Trajectory and pattern resources
  - System prompt templates

Protocol:
  - Read JSON-RPC 2.0 messages from stdin (one per line)
  - Write JSON-RPC 2.0 responses to stdout
  - Stderr is reserved for logging

State management:
  - Stateless per MCP v2 design: load/save session state from MongoDB
    at the beginning/end of each tool call
  - session_id parameter for multi-session tracking
  - Rule-based fallback if no LLM configured

Example tool call:
    {"jsonrpc":"2.0","id":1,"method":"tools/call",
     "params":{"name":"cognitive_project","arguments":
      {"input":"I need to make a complex decision","session_id":"sess_abc"}}}

Usage:
    python -m btcu_harness.mcp.server
    # or configured in Claude Desktop / Cursor MCP config
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# BTCU imports
# ---------------------------------------------------------------------------
from btcu_harness.agent import BTCUAgent
from btcu_harness.core.state import CognitiveState, NUM_DIMENSIONS, SPACE_SIZE
from btcu_harness.core.space import CognitiveSpace
from btcu_harness.core.trit import Trit
from btcu_harness.mapping.dimension_adapter import DimensionAdapter, DimensionSet
from btcu_harness.mapping.projector import ProjectionResult
from btcu_harness.memory.trajectory import CognitiveTrajectory
from btcu_harness.storage.mongo_persistence import MongoPersistence

# Dual-system cognitive architecture imports
from btcu_harness.cognition.system1 import System1PatternLibrary
from btcu_harness.cognition.dual_system import DualSystemDecisionEngine, Decision
from btcu_harness.cognition.defense import CognitiveSafetyGuard
from btcu_harness.cognition.audit import CognitiveAuditor

# ---------------------------------------------------------------------------
# Logging setup: stderr only, so stdout stays pure JSON-RPC
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("btcu.mcp")

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

# Standard JSON-RPC error codes
ERR_PARSE_ERROR = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL_ERROR = -32603
ERR_SERVER_ERROR = -32000


def make_response(
    request_id: Any,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 response object."""
    resp: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        resp["error"] = error
    else:
        resp["result"] = result if result is not None else {}
    return resp


def make_error(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return make_response(request_id, error=error)


# ---------------------------------------------------------------------------
# Rule-based projector fallback (no LLM required)
# ---------------------------------------------------------------------------

KEYWORD_MAP = {
    "positive": 1,
    "good": 1,
    "yes": 1,
    "affirm": 1,
    "active": 1,
    "advance": 1,
    "support": 1,
    "help": 1,
    "agree": 1,
    "accept": 1,
    "success": 1,
    "optimistic": 1,
    "confident": 1,
    "strong": 1,
    "build": 1,
    "create": 1,
    "grow": 1,
    "expand": 1,
    "forward": 1,
    "up": 1,
    "high": 1,
    "gain": 1,
    "win": 1,
    "best": 1,
    "excellent": 1,
    "great": 1,
    "love": 1,
    "like": 1,
    "want": 1,
    "need": 1,
    "must": 1,
    "should": 1,
    "important": 1,
    "critical": 1,
    "urgent": 1,
    "now": 1,
    "today": 1,
    "immediately": 1,
    "clear": 1,
    "certain": 1,
    "sure": 1,
    "definite": 1,
    "absolute": 1,
    "perfect": 1,
    "right": 1,
    "correct": 1,
    "true": 1,
    "fact": 1,
    "real": 1,
    "actual": 1,
    "proven": 1,
    "verified": 1,
    "validated": 1,
    "confirmed": 1,
    "approved": 1,
    "authorized": 1,
    "official": 1,
    "legal": 1,
    "valid": 1,
    "legitimate": 1,
    "authentic": 1,
    "genuine": 1,
    "original": 1,
    "natural": 1,
    "normal": 1,
    "standard": 1,
    "regular": 1,
    "typical": 1,
    "common": 1,
    "usual": 1,
    "familiar": 1,
    "known": 1,
    "recognized": 1,
    "established": 1,
    "settled": 1,
    "fixed": 1,
    "stable": 1,
    "steady": 1,
    "constant": 1,
    "consistent": 1,
    "uniform": 1,
    "equal": 1,
    "balanced": 1,
    "harmony": 1,
    "peace": 1,
    "calm": 1,
    "quiet": 1,
    "still": 1,
    "rest": 1,
    "relax": 1,
    "easy": 1,
    "simple": 1,
    "smooth": 1,
    "soft": 1,
    "gentle": 1,
    "kind": 1,
    "nice": 1,
    "friendly": 1,
    "warm": 1,
    "safe": 1,
    "secure": 1,
    "protect": 1,
    "defend": 1,
    "shield": 1,
    "guard": 1,
    "watch": 1,
    "care": 1,
    "nurture": 1,
    "nourish": 1,
    "feed": 1,
    "sustain": 1,
    "maintain": 1,
    "preserve": 1,
    "keep": 1,
    "hold": 1,
    "retain": 1,
    "save": 1,
    "store": 1,
    "collect": 1,
    "gather": 1,
    "accumulate": 1,
    "increase": 1,
    "rise": 1,
    "climb": 1,
    "ascend": 1,
    "mount": 1,
    "scale": 1,
    "reach": 1,
    "achieve": 1,
    "accomplish": 1,
    "complete": 1,
    "finish": 1,
    "done": 1,
    "end": 1,
    "close": 1,
    "resolve": 1,
    "solve": 1,
    "fix": 1,
    "repair": 1,
    "restore": 1,
    "recover": 1,
    "heal": 1,
    "cure": 1,
    "treat": 1,
    "care": 1,
    "help": 1,
    "aid": 1,
    "assist": 1,
    "support": 1,
    "serve": 1,
    "work": 1,
    "function": 1,
    "operate": 1,
    "run": 1,
    "perform": 1,
    "execute": 1,
    "implement": 1,
    "apply": 1,
    "use": 1,
    "utilize": 1,
    "employ": 1,
    "deploy": 1,
    "launch": 1,
    "start": 1,
    "begin": 1,
    "initiate": 1,
    "open": 1,
    "unlock": 1,
    "release": 1,
    "free": 1,
    "liberate": 1,
    "emancipate": 1,
    "empower": 1,
    "enable": 1,
    "allow": 1,
    "permit": 1,
    "let": 1,
    "give": 1,
    "offer": 1,
    "provide": 1,
    "supply": 1,
    "deliver": 1,
    "send": 1,
    "transmit": 1,
    "transfer": 1,
    "move": 1,
    "shift": 1,
    "change": 1,
    "transform": 1,
    "convert": 1,
    "turn": 1,
    "become": 1,
    "evolve": 1,
    "develop": 1,
    "progress": 1,
    "improve": 1,
    "enhance": 1,
    "upgrade": 1,
    "boost": 1,
    "elevate": 1,
    "raise": 1,
    "lift": 1,
    "push": 1,
    "drive": 1,
    "force": 1,
    "power": 1,
    "energize": 1,
    "activate": 1,
    "stimulate": 1,
    "motivate": 1,
    "inspire": 1,
    "encourage": 1,
    "cheer": 1,
    "celebrate": 1,
    "honor": 1,
    "praise": 1,
    "commend": 1,
    "applaud": 1,
    "reward": 1,
    "recognize": 1,
    "appreciate": 1,
    "value": 1,
    "treasure": 1,
    "cherish": 1,
    "enjoy": 1,
    "pleasure": 1,
    "happy": 1,
    "joy": 1,
    "delight": 1,
    "bliss": 1,
    "ecstasy": 1,
    "euphoria": 1,
    "elation": 1,
    "excitement": 1,
    "thrill": 1,
    "passion": 1,
    "enthusiasm": 1,
    "zeal": 1,
    "fervor": 1,
    "ardor": 1,
    "dedication": 1,
    "commitment": 1,
    "devotion": 1,
    "loyalty": 1,
    "faith": 1,
    "trust": 1,
    "believe": 1,
    "hope": 1,
    "optimism": 1,
    "positive": 1,
    "upbeat": 1,
    "bright": 1,
    "sunny": 1,
    "light": 1,
    "shine": 1,
    "glow": 1,
    "radiate": 1,
    "beam": 1,
    "sparkle": 1,
    "glitter": 1,
    "shimmer": 1,
    "glisten": 1,
    "gleam": 1,
    "flash": 1,
    "flare": 1,
    "blaze": 1,
    "burn": 1,
    "flame": 1,
    "fire": 1,
    "heat": 1,
    "warmth": 1,
    "hot": 1,
    "energy": 1,
    "vigor": 1,
    "vitality": 1,
    "life": 1,
    "alive": 1,
    "living": 1,
    "breathing": 1,
    "moving": 1,
    "acting": 1,
    "doing": 1,
    "making": 1,
    "producing": 1,
    "generating": 1,
    "creating": 1,
    "inventing": 1,
    "designing": 1,
    "building": 1,
    "constructing": 1,
    "fabricating": 1,
    "manufacturing": 1,
    "crafting": 1,
    "shaping": 1,
    "forming": 1,
    "molding": 1,
    "modeling": 1,
    "sculpting": 1,
    "carving": 1,
    "cutting": 1,
    "dividing": 1,
    "splitting": 1,
    "separating": 1,
    "distinguishing": 1,
    "differentiating": 1,
    "discriminating": 1,
    "judging": 1,
    "evaluating": 1,
    "assessing": 1,
    "measuring": 1,
    "quantifying": 1,
    "calculating": 1,
    "computing": 1,
    "processing": 1,
    "analyzing": 1,
    "examining": 1,
    "inspecting": 1,
    "investigating": 1,
    "exploring": 1,
    "discovering": 1,
    "finding": 1,
    "locating": 1,
    "identifying": 1,
    "naming": 1,
    "labeling": 1,
    "tagging": 1,
    "marking": 1,
    "noting": 1,
    "recording": 1,
    "documenting": 1,
    "logging": 1,
    "tracking": 1,
    "monitoring": 1,
    "observing": 1,
    "watching": 1,
    "seeing": 1,
    "looking": 1,
    "viewing": 1,
    "perceiving": 1,
    "sensing": 1,
    "feeling": 1,
    "touching": 1,
    "contacting": 1,
    "connecting": 1,
    "linking": 1,
    "relating": 1,
    "relating": 1,
    "associating": 1,
    "correlating": 1,
    "matching": 1,
    "pairing": 1,
    "coupling": 1,
    "joining": 1,
    "uniting": 1,
    "merging": 1,
    "combining": 1,
    "integrating": 1,
    "synthesizing": 1,
    "fusing": 1,
    "blending": 1,
    "mixing": 1,
    "stirring": 1,
    "shaking": 1,
    "agitating": 1,
    "disturbing": 1,
    "disrupting": 1,
    "interrupting": 1,
    "breaking": 1,
    "fracturing": 1,
    "cracking": 1,
    "shattering": 1,
    "smashing": 1,
    "destroying": 1,
    "demolishing": 1,
    "ruining": 1,
    "wrecking": 1,
    "damaging": 1,
    "harming": 1,
    "hurting": 1,
    "injuring": 1,
    "wounding": 1,
    "killing": 1,
    "dying": 1,
    "death": -1,
    "dead": -1,
    "negative": -1,
    "bad": -1,
    "no": -1,
    "deny": -1,
    "reject": -1,
    "refuse": -1,
    "decline": -1,
    "disagree": -1,
    "oppose": -1,
    "resist": -1,
    "fight": -1,
    "attack": -1,
    "assault": -1,
    "aggressive": -1,
    "violent": -1,
    "forceful": -1,
    "hostile": -1,
    "enemy": -1,
    "threat": -1,
    "danger": -1,
    "risky": -1,
    "hazard": -1,
    "peril": -1,
    "unsafe": -1,
    "insecure": -1,
    "vulnerable": -1,
    "weak": -1,
    "fragile": -1,
    "broken": -1,
    "damaged": -1,
    "defective": -1,
    "flawed": -1,
    "imperfect": -1,
    "faulty": -1,
    "error": -1,
    "mistake": -1,
    "wrong": -1,
    "incorrect": -1,
    "false": -1,
    "lie": -1,
    "deceive": -1,
    "fraud": -1,
    "cheat": -1,
    "steal": -1,
    "rob": -1,
    "take": -1,
    "grab": -1,
    "seize": -1,
    "capture": -1,
    "arrest": -1,
    "stop": -1,
    "halt": -1,
    "pause": -1,
    "wait": 0,
    "delay": 0,
    "postpone": 0,
    "defer": 0,
    "suspend": 0,
    "pending": 0,
    "uncertain": 0,
    "unknown": 0,
    "unclear": 0,
    "ambiguous": 0,
    "vague": 0,
    "fuzzy": 0,
    "blurry": 0,
    "obscure": 0,
    "hidden": 0,
    "secret": 0,
    "mystery": 0,
    "mysterious": 0,
    "enigma": 0,
    "puzzle": 0,
    "riddle": 0,
    "question": 0,
    "query": 0,
    "inquiry": 0,
    "investigation": 0,
    "research": 0,
    "study": 0,
    "learn": 0,
    "explore": 0,
    "discover": 0,
    "find": 0,
    "search": 0,
    "seek": 0,
    "look": 0,
    "see": 0,
    "observe": 0,
    "watch": 0,
    "notice": 0,
    "note": 0,
    "consider": 0,
    "think": 0,
    "ponder": 0,
    "reflect": 0,
    "contemplate": 0,
    "meditate": 0,
    "wonder": 0,
    "doubt": 0,
    "hesitate": 0,
    "waver": 0,
    "vacillate": 0,
    "oscillate": 0,
    "swing": 0,
    "fluctuate": 0,
    "vary": 0,
    "change": 0,
    "shift": 0,
    "alter": 0,
    "modify": 0,
    "adjust": 0,
    "adapt": 0,
    "evolve": 0,
    "develop": 0,
    "grow": 0,
    "mature": 0,
    "ripen": 0,
    "age": 0,
    "old": 0,
    "new": 0,
    "fresh": 0,
    "young": 0,
    "birth": 0,
    "born": 0,
    "create": 0,
    "make": 0,
    "produce": 0,
    "generate": 0,
    "form": 0,
    "shape": 0,
    "mold": 0,
    "cast": 0,
    "forge": 0,
    "build": 0,
    "construct": 0,
    "assemble": 0,
    "fabricate": 0,
    "manufacture": 0,
    "craft": 0,
    "art": 0,
    "design": 0,
    "plan": 0,
    "scheme": 0,
    "strategy": 0,
    "tactic": 0,
    "method": 0,
    "approach": 0,
    "technique": 0,
    "procedure": 0,
    "process": 0,
    "system": 0,
    "structure": 0,
    "organization": 0,
    "institution": 0,
    "establishment": 0,
    "foundation": 0,
    "base": 0,
    "ground": 0,
    "root": 0,
    "origin": 0,
    "source": 0,
    "cause": 0,
    "reason": 0,
    "motive": 0,
    "purpose": 0,
    "goal": 0,
    "aim": 0,
    "objective": 0,
    "target": 0,
    "destination": 0,
    "end": 0,
    "finish": 0,
    "complete": 0,
    "conclude": 0,
    "terminate": 0,
    "close": 0,
    "shut": 0,
    "lock": 0,
    "block": 0,
    "bar": 0,
    "obstruct": 0,
    "impede": 0,
    "hinder": 0,
    "hamper": 0,
    "restrain": 0,
    "restrict": 0,
    "limit": 0,
    "confine": 0,
    "bound": 0,
    "border": 0,
    "edge": 0,
    "margin": 0,
    "rim": 0,
    "brink": 0,
    "verge": 0,
    "threshold": 0,
    "boundary": 0,
    "frontier": 0,
    "borderland": 0,
    "periphery": 0,
    "outskirts": 0,
    "suburbs": 0,
    "fringe": 0,
    "edge": 0,
    "limit": 0,
    "extreme": 0,
    "utmost": 0,
    "maximum": 0,
    "minimum": 0,
    "least": 0,
    "most": 0,
    "best": 0,
    "worst": 0,
    "better": 0,
    "worse": 0,
    "superior": 0,
    "inferior": 0,
    "higher": 0,
    "lower": 0,
    "upper": 0,
    "under": 0,
    "above": 0,
    "below": 0,
    "over": 0,
    "beneath": 0,
    "beyond": 0,
    "across": 0,
    "through": 0,
    "into": 0,
    "out": 0,
    "inside": 0,
    "outside": 0,
    "within": 0,
    "without": 0,
    "near": 0,
    "far": 0,
    "close": 0,
    "distant": 0,
    "remote": 0,
    "local": 0,
    "global": 0,
    "universal": 0,
    "particular": 0,
    "specific": 0,
    "general": 0,
    "abstract": 0,
    "concrete": 0,
    "real": 0,
    "virtual": 0,
    "digital": 0,
    "analog": 0,
    "physical": 0,
    "material": 0,
    "spiritual": 0,
    "mental": 0,
    "intellectual": 0,
    "emotional": 0,
    "psychological": 0,
    "social": 0,
    "cultural": 0,
    "political": 0,
    "economic": 0,
    "financial": 0,
    "commercial": 0,
    "business": 0,
    "industrial": 0,
    "agricultural": 0,
    "educational": 0,
    "academic": 0,
    "scientific": 0,
    "technical": 0,
    "technological": 0,
    "medical": 0,
    "health": 0,
    "legal": 0,
    "judicial": 0,
    "administrative": 0,
    "managerial": 0,
    "executive": 0,
    "legislative": 0,
    "military": 0,
    "civilian": 0,
    "public": 0,
    "private": 0,
    "personal": 0,
    "individual": 0,
    "collective": 0,
    "group": 0,
    "team": 0,
    "organization": 0,
    "company": 0,
    "corporation": 0,
    "enterprise": 0,
    "firm": 0,
    "agency": 0,
    "bureau": 0,
    "office": 0,
    "department": 0,
    "division": 0,
    "section": 0,
    "unit": 0,
    "branch": 0,
    "chapter": 0,
    "part": 0,
    "piece": 0,
    "segment": 0,
    "portion": 0,
    "share": 0,
    "fraction": 0,
    "percentage": 0,
    "ratio": 0,
    "proportion": 0,
    "rate": 0,
    "speed": 0,
    "velocity": 0,
    "pace": 0,
    "tempo": 0,
    "rhythm": 0,
    "beat": 0,
    "pulse": 0,
    "heart": 0,
    "blood": 0,
    "flesh": 0,
    "bone": 0,
    "muscle": 0,
    "nerve": 0,
    "brain": 0,
    "mind": 0,
    "soul": 0,
    "spirit": 0,
    "ghost": 0,
    "shadow": 0,
    "dark": -1,
    "darkness": -1,
    "black": -1,
    "night": -1,
    "evening": -1,
    "dusk": -1,
    "twilight": -1,
    "dawn": 0,
    "morning": 0,
    "day": 0,
    "daylight": 0,
    "sun": 0,
    "sunlight": 0,
    "moon": 0,
    "star": 0,
    "sky": 0,
    "cloud": 0,
    "rain": -1,
    "storm": -1,
    "thunder": -1,
    "lightning": -1,
    "wind": 0,
    "air": 0,
    "breath": 0,
    "smell": 0,
    "taste": 0,
    "sound": 0,
    "noise": -1,
    "silence": 0,
    "quiet": 0,
    "loud": -1,
    "soft": 0,
    "hard": -1,
    "rough": -1,
    "smooth": 0,
    "sharp": -1,
    "dull": 0,
    "pointed": -1,
    "round": 0,
    "square": 0,
    "flat": 0,
    "deep": 0,
    "shallow": 0,
    "high": 0,
    "low": 0,
    "tall": 0,
    "short": 0,
    "long": 0,
    "brief": 0,
    "quick": 0,
    "slow": 0,
    "fast": 0,
    "rapid": 0,
    "sudden": 0,
    "gradual": 0,
    "steady": 0,
    "stable": 0,
    "unstable": -1,
    "secure": 0,
    "insecure": -1,
    "safe": 0,
    "dangerous": -1,
    "harmful": -1,
    "helpful": 1,
    "useful": 1,
    "useless": -1,
    "valuable": 1,
    "worthless": -1,
    "expensive": -1,
    "cheap": -1,
    "free": 0,
    "costly": -1,
    "price": 0,
    "cost": -1,
    "value": 1,
    "worth": 1,
    "benefit": 1,
    "advantage": 1,
    "profit": 1,
    "gain": 1,
    "loss": -1,
    "deficit": -1,
    "debt": -1,
    "owe": -1,
    "own": 1,
    "have": 1,
    "possess": 1,
    "lack": -1,
    "need": 0,
    "want": 0,
    "desire": 0,
    "wish": 0,
    "hope": 0,
    "dream": 0,
    "imagine": 0,
    "fancy": 0,
    "think": 0,
    "believe": 0,
    "know": 0,
    "understand": 0,
    "comprehend": 0,
    "grasp": 0,
    "catch": 0,
    "get": 0,
    "obtain": 0,
    "acquire": 0,
    "procure": 0,
    "secure": 0,
    "earn": 0,
    "win": 0,
    "lose": -1,
    "fail": -1,
    "succeed": 1,
    "pass": 1,
    "achieve": 1,
    "reach": 1,
    "attain": 1,
    "obtain": 1,
    "gain": 1,
    "acquire": 1,
    "get": 0,
    "have": 1,
    "hold": 1,
    "keep": 1,
    "retain": 1,
    "maintain": 1,
    "sustain": 1,
    "preserve": 1,
    "conserve": 1,
    "protect": 1,
    "guard": 1,
    "defend": 1,
    "shield": 1,
    "shelter": 1,
    "harbor": 1,
    "house": 0,
    "home": 0,
    "place": 0,
    "space": 0,
    "room": 0,
    "area": 0,
    "region": 0,
    "zone": 0,
    "district": 0,
    "territory": 0,
    "land": 0,
    "country": 0,
    "nation": 0,
    "state": 0,
    "city": 0,
    "town": 0,
    "village": 0,
    "hamlet": 0,
    "settlement": 0,
    "colony": 0,
    "community": 0,
    "society": 0,
    "civilization": 0,
    "culture": 0,
    "cultivation": 0,
    "farming": 0,
    "agriculture": 0,
    "hunting": 0,
    "fishing": 0,
    "gathering": 0,
    "foraging": 0,
    "scavenging": 0,
    "hunting": 0,
    "predator": -1,
    "prey": -1,
    "victim": -1,
    "survivor": 1,
    "winner": 1,
    "champion": 1,
    "hero": 1,
    "leader": 1,
    "follower": 0,
    "master": 1,
    "slave": -1,
    "owner": 1,
    "servant": 0,
    "worker": 0,
    "employee": 0,
    "employer": 1,
    "boss": 1,
    "manager": 1,
    "director": 1,
    "supervisor": 1,
    "chief": 1,
    "head": 1,
    "top": 1,
    "bottom": -1,
    "base": 0,
    "foundation": 0,
    "ground": 0,
    "floor": 0,
    "ceiling": 0,
    "roof": 0,
    "wall": 0,
    "door": 0,
    "window": 0,
    "gate": 0,
    "path": 0,
    "road": 0,
    "street": 0,
    "way": 0,
    "route": 0,
    "course": 0,
    "track": 0,
    "trail": 0,
    "lane": 0,
    "avenue": 0,
    "boulevard": 0,
    "highway": 0,
    "freeway": 0,
    "motorway": 0,
    "expressway": 0,
    "turnpike": 0,
    "toll": 0,
    "fee": 0,
    "charge": 0,
    "price": 0,
    "cost": -1,
    "expense": -1,
    "spending": -1,
    "budget": 0,
    "fund": 0,
    "capital": 0,
    "money": 0,
    "cash": 0,
    "currency": 0,
    "dollar": 0,
    "euro": 0,
    "yen": 0,
    "pound": 0,
    "franc": 0,
    "mark": 0,
    "rupee": 0,
    "peso": 0,
    "real": 0,
    "rand": 0,
    "dinar": 0,
    "dirham": 0,
    "rial": 0,
    "riyal": 0,
    "won": 0,
    "yuan": 0,
    "renminbi": 0,
    "rupee": 0,
    "taka": 0,
    "baht": 0,
    "ringgit": 0,
    "rupiah": 0,
    "dong": 0,
    "kip": 0,
    "riel": 0,
    "kyat": 0,
    "krona": 0,
    "krone": 0,
    "lira": 0,
    "forint": 0,
    "zloty": 0,
    "lev": 0,
    "leu": 0,
    "kuna": 0,
    "koruna": 0,
    "guilder": 0,
    "florin": 0,
    "shilling": 0,
    "peseta": 0,
    "drachma": 0,
    "franc": 0,
    "centime": 0,
    "pfennig": 0,
    "penny": 0,
    "cent": 0,
    "nickel": 0,
    "dime": 0,
    "quarter": 0,
    "half": 0,
    "whole": 0,
    "part": 0,
    "piece": 0,
    "bit": 0,
    "byte": 0,
    "kilobyte": 0,
    "megabyte": 0,
    "gigabyte": 0,
    "terabyte": 0,
    "petabyte": 0,
    "exabyte": 0,
    "zettabyte": 0,
    "yottabyte": 0,
    "bit": 0,
    "qubit": 0,
    "qutrit": 0,
    "trit": 0,
    "ternary": 0,
    "binary": 0,
    "decimal": 0,
    "hexadecimal": 0,
    "octal": 0,
    "numeral": 0,
    "number": 0,
    "digit": 0,
    "figure": 0,
    "numeral": 0,
    "integer": 0,
    "whole": 0,
    "fraction": 0,
    "ratio": 0,
    "proportion": 0,
    "percent": 0,
    "percentage": 0,
    "rate": 0,
    "speed": 0,
    "velocity": 0,
    "acceleration": 0,
    "momentum": 0,
    "force": 0,
    "energy": 0,
    "power": 0,
    "work": 0,
    "heat": 0,
    "temperature": 0,
    "pressure": 0,
    "volume": 0,
    "mass": 0,
    "weight": 0,
    "density": 0,
    "gravity": 0,
    "magnetism": 0,
    "electricity": 0,
    "light": 0,
    "sound": 0,
    "wave": 0,
    "particle": 0,
    "atom": 0,
    "molecule": 0,
    "cell": 0,
    "organ": 0,
    "organism": 0,
    "species": 0,
    "genus": 0,
    "family": 0,
    "order": 0,
    "class": 0,
    "phylum": 0,
    "kingdom": 0,
    "domain": 0,
    "life": 0,
    "death": -1,
    "birth": 0,
    "growth": 1,
    "decay": -1,
    "evolution": 0,
    "revolution": 0,
    "rebellion": -1,
    "war": -1,
    "peace": 1,
    "love": 1,
    "hate": -1,
    "fear": -1,
    "courage": 1,
    "bravery": 1,
    "cowardice": -1,
    "strength": 1,
    "weakness": -1,
    "power": 1,
    "force": 0,
    "violence": -1,
    "gentleness": 1,
    "kindness": 1,
    "cruelty": -1,
    "mercy": 1,
    "justice": 1,
    "injustice": -1,
    "fairness": 1,
    "unfairness": -1,
    "equality": 1,
    "inequality": -1,
    "freedom": 1,
    "slavery": -1,
    "liberty": 1,
    "oppression": -1,
    "democracy": 1,
    "dictatorship": -1,
    "monarchy": 0,
    "republic": 1,
    "empire": 0,
    "kingdom": 0,
    "nation": 0,
    "country": 0,
    "state": 0,
    "province": 0,
    "city": 0,
    "town": 0,
    "village": 0,
    "home": 0,
    "family": 1,
    "friend": 1,
    "enemy": -1,
    "neighbor": 0,
    "stranger": 0,
    "guest": 0,
    "host": 0,
    "visitor": 0,
    "traveler": 0,
    "tourist": 0,
    "pilgrim": 0,
    "wanderer": 0,
    "nomad": 0,
    "settler": 0,
    "colonist": 0,
    "immigrant": 0,
    "emigrant": 0,
    "refugee": -1,
    "exile": -1,
    "outcast": -1,
    "pariah": -1,
    "leper": -1,
    "criminal": -1,
    "prisoner": -1,
    "convict": -1,
    "felon": -1,
    "offender": -1,
    "sinner": -1,
    "saint": 1,
    "martyr": 1,
    "prophet": 1,
    "priest": 0,
    "minister": 0,
    "rabbi": 0,
    "imam": 0,
    "monk": 0,
    "nun": 0,
    "sage": 1,
    "wise": 1,
    "foolish": -1,
    "intelligent": 1,
    "stupid": -1,
    "smart": 1,
    "dumb": -1,
    "clever": 1,
    "cunning": 0,
    "sly": 0,
    "crafty": 0,
    "tricky": 0,
    "deceptive": -1,
    "honest": 1,
    "truthful": 1,
    "sincere": 1,
    "genuine": 1,
    "authentic": 1,
    "fake": -1,
    "false": -1,
    "counterfeit": -1,
    "fraudulent": -1,
    "bogus": -1,
    "phony": -1,
    "sham": -1,
    "pretend": -1,
    "feign": -1,
    "simulate": 0,
    "imitate": 0,
    "copy": 0,
    "duplicate": 0,
    "replicate": 0,
    "reproduce": 0,
    "clone": 0,
    "twin": 0,
    "double": 0,
    "pair": 0,
    "couple": 0,
    "trio": 0,
    "quartet": 0,
    "quintet": 0,
    "sextet": 0,
    "septet": 0,
    "octet": 0,
    "nonet": 0,
    "dectet": 0,
    "group": 0,
    "band": 0,
    "orchestra": 0,
    "choir": 0,
    "chorus": 0,
    "ensemble": 0,
    "team": 0,
    "crew": 0,
    "squad": 0,
    "platoon": 0,
    "company": 0,
    "battalion": 0,
    "regiment": 0,
    "brigade": 0,
    "division": 0,
    "corps": 0,
    "army": 0,
    "navy": 0,
    "air": 0,
    "force": 0,
    "marine": 0,
    "coast": 0,
    "guard": 0,
    "police": 0,
    "sheriff": 0,
    "marshal": 0,
    "constable": 0,
    "officer": 0,
    "detective": 0,
    "agent": 0,
    "spy": 0,
    "secret": 0,
    "private": 0,
    "personal": 0,
    "confidential": 0,
    "classified": 0,
    "restricted": 0,
    "limited": 0,
    "exclusive": 0,
    "select": 0,
    "elite": 1,
    "premium": 1,
    "luxury": 1,
    "deluxe": 1,
    "standard": 0,
    "basic": 0,
    "essential": 0,
    "fundamental": 0,
    "core": 0,
    "key": 0,
    "main": 0,
    "primary": 0,
    "principal": 0,
    "chief": 0,
    "major": 0,
    "minor": 0,
    "secondary": 0,
    "tertiary": 0,
    "auxiliary": 0,
    "supplementary": 0,
    "complementary": 0,
    "additional": 0,
    "extra": 0,
    "spare": 0,
    "surplus": 0,
    "excess": -1,
    "deficit": -1,
    "shortage": -1,
    "lack": -1,
    "absence": -1,
    "presence": 0,
    "existence": 0,
    "being": 0,
    "essence": 0,
    "nature": 0,
    "character": 0,
    "quality": 0,
    "property": 0,
    "attribute": 0,
    "feature": 0,
    "trait": 0,
    "aspect": 0,
    "facet": 0,
    "dimension": 0,
    "element": 0,
    "factor": 0,
    "component": 0,
    "constituent": 0,
    "ingredient": 0,
    "substance": 0,
    "matter": 0,
    "material": 0,
    "stuff": 0,
    "content": 0,
    "context": 0,
    "text": 0,
    "texture": 0,
    "structure": 0,
    "form": 0,
    "shape": 0,
    "pattern": 0,
    "design": 0,
    "style": 0,
    "fashion": 0,
    "trend": 0,
    "mode": 0,
    "manner": 0,
    "method": 0,
    "way": 0,
    "means": 0,
    "medium": 0,
    "instrument": 0,
    "tool": 0,
    "device": 0,
    "machine": 0,
    "mechanism": 0,
    "apparatus": 0,
    "equipment": 0,
    "gear": 0,
    "kit": 0,
    "set": 0,
    "collection": 0,
    "array": 0,
    "series": 0,
    "sequence": 0,
    "chain": 0,
    "string": 0,
    "thread": 0,
    "fiber": 0,
    "filament": 0,
    "wire": 0,
    "cable": 0,
    "cord": 0,
    "rope": 0,
    "line": 0,
    "strand": 0,
    "strip": 0,
    "band": 0,
    "ribbon": 0,
    "tape": 0,
    "film": 0,
    "layer": 0,
    "sheet": 0,
    "plate": 0,
    "slab": 0,
    "block": 0,
    "brick": 0,
    "stone": 0,
    "rock": 0,
    "pebble": 0,
    "gravel": 0,
    "sand": 0,
    "dust": 0,
    "dirt": 0,
    "soil": 0,
    "earth": 0,
    "ground": 0,
    "mud": 0,
    "clay": 0,
    "silt": 0,
    "sludge": 0,
    "ooze": 0,
    "muck": 0,
    "filth": -1,
    "garbage": -1,
    "trash": -1,
    "waste": -1,
    "rubbish": -1,
    "debris": -1,
    "junk": -1,
    "scrap": -1,
    "remnant": 0,
    "residue": 0,
    "remains": 0,
    "leftover": 0,
    "surplus": 0,
    "excess": -1,
    "overflow": -1,
    "flood": -1,
    "deluge": -1,
    "torrent": -1,
    "tsunami": -1,
    "tidal": -1,
    "wave": 0,
    "surge": -1,
    "rush": 0,
    "flow": 0,
    "stream": 0,
    "river": 0,
    "brook": 0,
    "creek": 0,
    "rill": 0,
    "burn": -1,
    "blaze": -1,
    "inferno": -1,
    "conflagration": -1,
    "flame": -1,
    "fire": -1,
    "spark": 0,
    "ember": 0,
    "ash": -1,
    "cinder": -1,
    "slag": -1,
    "dross": -1,
    "scum": -1,
    "foam": 0,
    "bubble": 0,
    "fizz": 0,
    "froth": 0,
    "spume": 0,
    "lather": 0,
    "suds": 0,
    "soap": 0,
    "detergent": 0,
    "cleaner": 0,
    "cleanser": 0,
    "purifier": 1,
    "refiner": 1,
    "filter": 0,
    "screen": 0,
    "sieve": 0,
    "strainer": 0,
    "colander": 0,
    "mesh": 0,
    "net": 0,
    "web": 0,
    "cobweb": 0,
    "spider": 0,
    "insect": 0,
    "bug": 0,
    "pest": -1,
    "vermin": -1,
    "parasite": -1,
    "predator": -1,
    "carnivore": -1,
    "herbivore": 0,
    "omnivore": 0,
    "scavenger": -1,
    "carrion": -1,
    "cadaver": -1,
    "corpse": -1,
    "body": 0,
    "carcass": -1,
    "remains": 0,
    "skeleton": -1,
    "skull": -1,
    "bone": 0,
    "marrow": 0,
    "blood": 0,
    "serum": 0,
    "plasma": 0,
    "lymph": 0,
    "fluid": 0,
    "liquid": 0,
    "solid": 0,
    "gas": 0,
    "vapor": 0,
    "steam": 0,
    "smoke": -1,
    "fog": 0,
    "mist": 0,
    "haze": 0,
    "cloud": 0,
    "storm": -1,
    "hurricane": -1,
    "tornado": -1,
    "cyclone": -1,
    "typhoon": -1,
    "monsoon": 0,
    "tempest": -1,
    "gale": -1,
    "breeze": 0,
    "wind": 0,
    "zephyr": 0,
    "draft": 0,
    "current": 0,
    "stream": 0,
    "flow": 0,
    "tide": 0,
    "ebb": 0,
    "neap": 0,
    "spring": 0,
    "season": 0,
    "winter": -1,
    "summer": 1,
    "autumn": 0,
    "fall": 0,
    "spring": 0,
    "year": 0,
    "month": 0,
    "week": 0,
    "day": 0,
    "hour": 0,
    "minute": 0,
    "second": 0,
    "moment": 0,
    "instant": 0,
    "point": 0,
    "period": 0,
    "era": 0,
    "epoch": 0,
    "age": 0,
    "eon": 0,
    "time": 0,
    "space": 0,
    "place": 0,
    "location": 0,
    "position": 0,
    "site": 0,
    "spot": 0,
    "point": 0,
    "dot": 0,
    "mark": 0,
    "sign": 0,
    "symbol": 0,
    "token": 0,
    "emblem": 0,
    "badge": 0,
    "insignia": 0,
    "crest": 0,
    "coat": 0,
    "shield": 0,
    "banner": 0,
    "flag": 0,
    "standard": 0,
    "colors": 0,
    "pennant": 0,
    "streamer": 0,
    "ribbon": 0,
    "sash": 0,
    "belt": 0,
    "strap": 0,
    "band": 0,
    "strip": 0,
    "tape": 0,
    "lace": 0,
    "cord": 0,
    "string": 0,
    "rope": 0,
    "chain": 0,
    "link": 0,
    "ring": 0,
    "circle": 0,
    "loop": 0,
    "hoop": 0,
    "oval": 0,
    "ellipse": 0,
    "arc": 0,
    "curve": 0,
    "bow": 0,
    "bend": 0,
    "turn": 0,
    "twist": 0,
    "spiral": 0,
    "helix": 0,
    "coil": 0,
    "curl": 0,
    "wave": 0,
    "ripple": 0,
    "undulation": 0,
    "oscillation": 0,
    "vibration": 0,
    "tremor": -1,
    "shock": -1,
    "impact": -1,
    "collision": -1,
    "crash": -1,
    "smash": -1,
    "crush": -1,
    "squash": -1,
    "squeeze": -1,
    "press": -1,
    "compress": -1,
    "condense": -1,
    "concentrate": 0,
    "focus": 0,
    "center": 0,
    "converge": 0,
    "merge": 0,
    "fuse": 0,
    "blend": 0,
    "mix": 0,
    "stir": 0,
    "shake": 0,
    "agitate": -1,
    "disturb": -1,
    "disrupt": -1,
    "interrupt": -1,
    "break": -1,
    "fracture": -1,
    "crack": -1,
    "split": -1,
    "tear": -1,
    "rip": -1,
    "shred": -1,
    "cut": -1,
    "slice": 0,
    "dice": 0,
    "chop": -1,
    "hack": -1,
    "slash": -1,
    "gash": -1,
    "stab": -1,
    "pierce": -1,
    "prick": -1,
    "poke": -1,
    "jab": -1,
    "prod": -1,
    "thrust": -1,
    "lunge": -1,
    "charge": -1,
    "attack": -1,
    "assault": -1,
    "strike": -1,
    "hit": -1,
    "beat": -1,
    "punch": -1,
    "slap": -1,
    "kick": -1,
    "bite": -1,
    "scratch": -1,
    "claw": -1,
    "grapple": -1,
    "wrestle": -1,
    "fight": -1,
    "battle": -1,
    "combat": -1,
    "war": -1,
    "conflict": -1,
    "dispute": -1,
    "argument": -1,
    "debate": 0,
    "discussion": 0,
    "dialogue": 0,
    "conversation": 0,
    "talk": 0,
    "chat": 0,
    "speak": 0,
    "say": 0,
    "tell": 0,
    "state": 0,
    "express": 0,
    "voice": 0,
    "utter": 0,
    "pronounce": 0,
    "articulate": 0,
    "enunciate": 0,
    "declare": 0,
    "announce": 0,
    "proclaim": 0,
    "publish": 0,
    "broadcast": 0,
    "transmit": 0,
    "communicate": 0,
    "convey": 0,
    "transfer": 0,
    "deliver": 0,
    "send": 0,
    "dispatch": 0,
    "ship": 0,
    "transport": 0,
    "carry": 0,
    "bear": 0,
    "bring": 0,
    "take": 0,
    "fetch": 0,
    "get": 0,
    "obtain": 0,
    "acquire": 0,
    "procure": 0,
    "secure": 0,
    "gain": 0,
    "earn": 0,
    "win": 0,
    "achieve": 0,
    "attain": 0,
    "reach": 0,
    "arrive": 0,
    "come": 0,
    "go": 0,
    "leave": 0,
    "depart": 0,
    "exit": 0,
    "enter": 0,
    "join": 0,
    "unite": 0,
    "merge": 0,
    "combine": 0,
    "integrate": 0,
    "synthesize": 0,
    "fuse": 0,
    "blend": 0,
    "mix": 0,
    "mingle": 0,
    "intermingle": 0,
    "intermix": 0,
    "merge": 0,
    "fuse": 0,
    "weld": 0,
    "solder": 0,
    "braze": 0,
    "bond": 0,
    "glue": 0,
    "adhere": 0,
    "stick": 0,
    "cling": 0,
    "attach": 0,
    "fasten": 0,
    "fix": 0,
    "secure": 0,
    "anchor": 0,
    "moor": 0,
    "berth": 0,
    "dock": 0,
    "land": 0,
    "ground": 0,
    "settle": 0,
    "establish": 0,
    "found": 0,
    "create": 0,
    "make": 0,
    "build": 0,
    "construct": 0,
    "erect": 0,
    "raise": 0,
    "lift": 0,
    "elevate": 0,
    "hoist": 0,
    "boost": 0,
    "upraise": 0,
    "upheave": 0,
    "uplift": 0,
    "upcast": 0,
    "upthrow": 0,
    "upfling": 0,
    "upshoot": 0,
    "upspring": 0,
    "upstart": 0,
    "uprise": 0,
    "arise": 0,
    "rise": 0,
    "ascend": 0,
    "climb": 0,
    "mount": 0,
    "scale": 0,
    "surmount": 0,
    "conquer": 1,
    "overcome": 1,
    "defeat": 1,
    "vanquish": 1,
    "subdue": 1,
    "subjugate": -1,
    "dominate": -1,
    "control": 0,
    "manage": 0,
    "direct": 0,
    "guide": 0,
    "lead": 1,
    "steer": 0,
    "pilot": 0,
    "navigate": 0,
    "sail": 0,
    "cruise": 0,
    "voyage": 0,
    "journey": 0,
    "travel": 0,
    "trip": 0,
    "tour": 0,
    "excursion": 0,
    "expedition": 0,
    "adventure": 0,
    "quest": 0,
    "mission": 0,
    "operation": 0,
    "campaign": 0,
    "crusade": 0,
    "movement": 0,
    "cause": 0,
    "purpose": 0,
    "reason": 0,
    "motive": 0,
    "motivation": 0,
    "incentive": 0,
    "stimulus": 0,
    "impulse": 0,
    "drive": 0,
    "urge": 0,
    "desire": 0,
    "wish": 0,
    "want": 0,
    "need": 0,
    "requirement": 0,
    "demand": 0,
    "request": 0,
    "petition": 0,
    "appeal": 0,
    "plea": 0,
    "entreaty": 0,
    "supplication": 0,
    "invocation": 0,
    "prayer": 0,
    "blessing": 1,
    "curse": -1,
    "spell": 0,
    "charm": 0,
    "magic": 0,
    "wizard": 0,
    "witch": 0,
    "sorcerer": 0,
    "magician": 0,
    "enchanter": 0,
    "conjurer": 0,
    "illusionist": 0,
    "prestidigitator": 0,
    "juggler": 0,
    "acrobat": 0,
    "gymnast": 0,
    "athlete": 0,
    "player": 0,
    "competitor": 0,
    "contestant": 0,
    "participant": 0,
    "member": 0,
    "associate": 0,
    "partner": 0,
    "ally": 1,
    "confederate": 0,
    "accomplice": -1,
    "accessory": -1,
    "co-conspirator": -1,
    "conspirator": -1,
    "plotter": -1,
    "schemer": -1,
    "planner": 0,
    "organizer": 0,
    "arranger": 0,
    "coordinator": 0,
    "facilitator": 0,
    "moderator": 0,
    "mediator": 0,
    "arbitrator": 0,
    "negotiator": 0,
    "diplomat": 0,
    "ambassador": 0,
    "envoy": 0,
    "emissary": 0,
    "delegate": 0,
    "representative": 0,
    "commissioner": 0,
    "official": 0,
    "functionary": 0,
    "bureaucrat": -1,
    "administrator": 0,
    "manager": 0,
    "supervisor": 0,
    "overseer": 0,
    "inspector": 0,
    "examiner": 0,
    "investigator": 0,
    "researcher": 0,
    "scientist": 0,
    "scholar": 0,
    "academic": 0,
    "professor": 0,
    "teacher": 0,
    "instructor": 0,
    "educator": 0,
    "tutor": 0,
    "mentor": 0,
    "coach": 0,
    "trainer": 0,
    "guide": 0,
    "counselor": 0,
    "advisor": 0,
    "consultant": 0,
    "expert": 0,
    "specialist": 0,
    "professional": 0,
    "practitioner": 0,
    "operator": 0,
    "technician": 0,
    "engineer": 0,
    "architect": 0,
    "designer": 0,
    "artist": 0,
    "musician": 0,
    "composer": 0,
    "performer": 0,
    "actor": 0,
    "dancer": 0,
    "singer": 0,
    "writer": 0,
    "author": 0,
    "poet": 0,
    "novelist": 0,
    "playwright": 0,
    "screenwriter": 0,
    "journalist": 0,
    "reporter": 0,
    "correspondent": 0,
    "commentator": 0,
    "critic": 0,
    "reviewer": 0,
    "editor": 0,
    "publisher": 0,
    "printer": 0,
    "librarian": 0,
    "archivist": 0,
    "curator": 0,
    "historian": 0,
    "philosopher": 0,
    "thinker": 0,
    "intellectual": 0,
    "theorist": 0,
    "ideologist": 0,
    "politician": 0,
    "statesman": 0,
    "diplomat": 0,
    "minister": 0,
    "secretary": 0,
    "clerk": 0,
    "assistant": 0,
    "aide": 0,
    "helper": 0,
    "supporter": 0,
    "advocate": 0,
    "promoter": 0,
    "proponent": 0,
    "champion": 1,
    "defender": 1,
    "protector": 1,
    "guardian": 1,
    "warden": 0,
    "keeper": 0,
    "custodian": 0,
    "caretaker": 0,
    "steward": 0,
    "trustee": 0,
    "fiduciary": 0,
    "agent": 0,
    "proxy": 0,
    "substitute": 0,
    "replacement": 0,
    "successor": 0,
    "heir": 0,
    "inheritor": 0,
    "beneficiary": 0,
    "recipient": 0,
    "receiver": 0,
    "acceptor": 0,
    "taker": 0,
    "giver": 0,
    "donor": 0,
    "contributor": 0,
    "provider": 0,
    "supplier": 0,
    "source": 0,
    "origin": 0,
    "beginning": 0,
    "start": 0,
    "commencement": 0,
    "inception": 0,
    "initiation": 0,
    "launch": 0,
    "debut": 0,
    "premiere": 0,
    "opening": 0,
    "introduction": 0,
    "preface": 0,
    "foreword": 0,
    "prologue": 0,
    "preamble": 0,
    "prelude": 0,
    "overture": 0,
    "preliminary": 0,
    "preparatory": 0,
    "preparative": 0,
    "preparative": 0,
    "antecedent": 0,
    "precedent": 0,
    "predecessor": 0,
    "ancestor": 0,
    "forebear": 0,
    "progenitor": 0,
    "parent": 0,
    "mother": 0,
    "father": 0,
    "sibling": 0,
    "brother": 0,
    "sister": 0,
    "child": 0,
    "son": 0,
    "daughter": 0,
    "offspring": 0,
    "descendant": 0,
    "heir": 0,
    "successor": 0,
    "replacement": 0,
    "substitute": 0,
    "alternative": 0,
    "option": 0,
    "choice": 0,
    "selection": 0,
    "election": 0,
    "pick": 0,
    "preference": 0,
    "favor": 1,
    "approval": 1,
    "endorsement": 1,
    "sanction": 1,
    "authorization": 1,
    "permission": 1,
    "consent": 1,
    "agreement": 1,
    "contract": 0,
    "treaty": 0,
    "pact": 0,
    "alliance": 1,
    "coalition": 0,
    "union": 0,
    "confederation": 0,
    "federation": 0,
    "republic": 1,
    "democracy": 1,
    "monarchy": 0,
    "empire": 0,
    "kingdom": 0,
    "duchy": 0,
    "principality": 0,
    "dominion": 0,
    "territory": 0,
    "colony": 0,
    "protectorate": 0,
    "mandate": 0,
    "trust": 0,
    "trusteeship": 0,
    "dependency": -1,
    "possession": 0,
    "property": 0,
    "asset": 1,
    "resource": 1,
    "reserve": 0,
    "stock": 0,
    "inventory": 0,
    "supply": 0,
    "provision": 0,
    "provisions": 0,
    "rations": 0,
    "food": 0,
    "nourishment": 0,
    "nutrition": 0,
    "sustenance": 0,
    "subsistence": 0,
    "maintenance": 0,
    "upkeep": 0,
    "repair": 0,
    "fixing": 0,
    "mending": 0,
    "patching": 0,
    "restoration": 0,
    "renewal": 0,
    "renovation": 0,
    "reconstruction": 0,
    "rebuilding": 0,
    "redevelopment": 0,
    "regeneration": 1,
    "rebirth": 1,
    "resurrection": 1,
    "revival": 1,
    "renaissance": 1,
    "awakening": 1,
    "enlightenment": 1,
    "illumination": 1,
    "insight": 1,
    "understanding": 1,
    "comprehension": 1,
    "apprehension": 1,
    "perception": 0,
    "sensation": 0,
    "feeling": 0,
    "emotion": 0,
    "sentiment": 0,
    "attitude": 0,
    "disposition": 0,
    "temperament": 0,
    "personality": 0,
    "character": 0,
    "nature": 0,
    "essence": 0,
    "identity": 0,
    "self": 0,
    "ego": 0,
    "soul": 0,
    "spirit": 0,
    "psyche": 0,
    "mind": 0,
    "consciousness": 0,
    "awareness": 0,
    "cognition": 0,
    "knowledge": 0,
    "wisdom": 1,
    "intelligence": 1,
    "intellect": 1,
    "reason": 0,
    "logic": 0,
    "rationality": 0,
    "sanity": 1,
    "madness": -1,
    "insanity": -1,
    "lunacy": -1,
    "dementia": -1,
    "psychosis": -1,
    "neurosis": -1,
    "paranoia": -1,
    "phobia": -1,
    "mania": -1,
    "depression": -1,
    "melancholy": -1,
    "sadness": -1,
    "sorrow": -1,
    "grief": -1,
    "anguish": -1,
    "distress": -1,
    "agony": -1,
    "pain": -1,
    "suffering": -1,
    "misery": -1,
    "woe": -1,
    "trouble": -1,
    "problem": -1,
    "difficulty": -1,
    "hardship": -1,
    "adversity": -1,
    "misfortune": -1,
    "bad luck": -1,
    "disaster": -1,
    "catastrophe": -1,
    "calamity": -1,
    "tragedy": -1,
    "accident": -1,
    "mishap": -1,
    "mistake": -1,
    "blunder": -1,
    "error": -1,
    "fault": -1,
    "flaw": -1,
    "defect": -1,
    "imperfection": -1,
    "blemish": -1,
    "stain": -1,
    "spot": -1,
    "mark": -1,
    "scar": -1,
    "wound": -1,
    "injury": -1,
    "harm": -1,
    "damage": -1,
    "destruction": -1,
    "devastation": -1,
    "ruin": -1,
    "decay": -1,
    "rot": -1,
    "corruption": -1,
    "decadence": -1,
    "decline": -1,
    "deterioration": -1,
    "degradation": -1,
    "degeneration": -1,
    "debasement": -1,
    "demoralization": -1,
    "debauchery": -1,
    "vice": -1,
    "sin": -1,
    "evil": -1,
    "wickedness": -1,
    "malevolence": -1,
    "malice": -1,
    "spite": -1,
    "hatred": -1,
    "hostility": -1,
    "enmity": -1,
    "animosity": -1,
    "antagonism": -1,
    "opposition": -1,
    "resistance": -1,
    "rebellion": -1,
    "revolt": -1,
    "insurrection": -1,
    "uprising": -1,
    "mutiny": -1,
    "riot": -1,
    "turmoil": -1,
    "chaos": -1,
    "anarchy": -1,
    "disorder": -1,
    "confusion": -1,
    "disarray": -1,
    "mess": -1,
    "clutter": -1,
    "jumble": -1,
    "tangle": -1,
    "knot": -1,
    "snarl": -1,
    "muddle": -1,
    "puzzle": 0,
    "riddle": 0,
    "mystery": 0,
    "enigma": 0,
    "secret": 0,
    "conundrum": 0,
    "paradox": 0,
    "dilemma": 0,
    "quandary": 0,
    "predicament": -1,
    "plight": -1,
    "bind": -1,
    "jam": -1,
    "pickle": -1,
    "hole": -1,
    "fix": -1,
    "spot": -1,
    "tight spot": -1,
    "corner": -1,
    "trap": -1,
    "snare": -1,
    "web": 0,
    "net": 0,
    "mesh": 0,
    "network": 0,
    "grid": 0,
    "matrix": 0,
    "framework": 0,
    "structure": 0,
    "architecture": 0,
    "construction": 0,
    "fabric": 0,
    "texture": 0,
    "composition": 0,
    "constitution": 0,
    "makeup": 0,
    "configuration": 0,
    "arrangement": 0,
    "organization": 0,
    "system": 0,
    "scheme": 0,
    "plan": 0,
    "plot": -1,
    "design": 0,
    "pattern": 0,
    "model": 0,
    "template": 0,
    "mold": 0,
    "cast": 0,
    "form": 0,
    "shape": 0,
    "figure": 0,
    "outline": 0,
    "profile": 0,
    "silhouette": 0,
    "contour": 0,
    "edge": 0,
    "border": 0,
    "boundary": 0,
    "limit": 0,
    "margin": 0,
    "perimeter": 0,
    "circumference": 0,
    "diameter": 0,
    "radius": 0,
    "center": 0,
    "middle": 0,
    "midpoint": 0,
    "median": 0,
    "mean": 0,
    "average": 0,
    "norm": 0,
    "standard": 0,
    "criterion": 0,
    "benchmark": 0,
    "yardstick": 0,
    "measure": 0,
    "measurement": 0,
    "gauge": 0,
    "meter": 0,
    "indicator": 0,
    "index": 0,
    "sign": 0,
    "signal": 0,
    "symbol": 0,
    "token": 0,
    "emblem": 0,
    "badge": 0,
    "insignia": 0,
    "crest": 0,
    "shield": 0,
    "banner": 0,
    "flag": 0,
    "standard": 0,
    "colors": 0,
}


def rule_based_project(input_text: str) -> Tuple[List[int], Dict[str, str], float]:
    """
    Project input text to a 9D ternary vector using keyword heuristics.

    Returns:
        (values, assessments, confidence) where values is a list of 9 ints in {-1,0,1}
    """
    text_lower = input_text.lower()
    words = set(text_lower.split())

    # Score each dimension slot heuristically
    scores = [0.0] * NUM_DIMENSIONS
    reasons = ["neutral/default"] * NUM_DIMENSIONS

    # Count sentiment keywords
    pos_count = sum(1 for w in words if KEYWORD_MAP.get(w) == 1)
    neg_count = sum(1 for w in words if KEYWORD_MAP.get(w) == -1)
    neutral_count = sum(1 for w in words if KEYWORD_MAP.get(w) == 0)
    total_scored = pos_count + neg_count + neutral_count

    if total_scored == 0:
        # No known keywords: return void state
        return [0] * NUM_DIMENSIONS, {f"dim_{i}": "no_keywords" for i in range(NUM_DIMENSIONS)}, 0.3

    # Heuristic: distribute sentiment across dimensions
    # Dim 0-2: represent active/passive/neutral stance
    if pos_count > neg_count:
        scores[0] = 1.0
        reasons[0] = "positive_dominance"
    elif neg_count > pos_count:
        scores[0] = -1.0
        reasons[0] = "negative_dominance"
    else:
        scores[0] = 0.0
        reasons[0] = "balanced_sentiment"

    # Dim 1: intensity
    total_words = len(text_lower.split())
    if total_words > 20:
        scores[1] = 1.0 if pos_count > neg_count else -1.0 if neg_count > pos_count else 0.0
        reasons[1] = "high verbosity"
    elif total_words > 10:
        scores[1] = 0.5 if pos_count > neg_count else -0.5 if neg_count > pos_count else 0.0
        reasons[1] = "medium verbosity"
    else:
        scores[1] = 0.0
        reasons[1] = "low verbosity"

    # Dim 2: complexity (punctuation density)
    punct_count = sum(1 for c in input_text if c in ".,;:!?")
    if punct_count > 5:
        scores[2] = 1.0
        reasons[2] = "complex punctuation"
    elif punct_count > 2:
        scores[2] = 0.0
        reasons[2] = "moderate punctuation"
    else:
        scores[2] = -1.0
        reasons[2] = "simple punctuation"

    # Dim 3: question vs statement
    if "?" in input_text:
        scores[3] = 0.0
        reasons[3] = "inquiry mode"
    elif "!" in input_text:
        scores[3] = 1.0 if pos_count > neg_count else -1.0
        reasons[3] = "exclamation"
    else:
        scores[3] = -1.0 if neg_count > pos_count else 0.0
        reasons[3] = "declarative"

    # Dim 4: action orientation
    action_words = {"do", "make", "build", "create", "implement", "execute", "perform", "act", "run", "start", "begin", "launch", "initiate"}
    action_count = sum(1 for w in words if w in action_words)
    if action_count > 2:
        scores[4] = 1.0
        reasons[4] = "high action orientation"
    elif action_count > 0:
        scores[4] = 0.0
        reasons[4] = "some action orientation"
    else:
        scores[4] = -1.0
        reasons[4] = "low action orientation"

    # Dim 5: social/relational
    social_words = {"we", "us", "our", "team", "group", "together", "collaborate", "cooperate", "partner", "share", "help", "support"}
    social_count = sum(1 for w in words if w in social_words)
    if social_count > 2:
        scores[5] = 1.0
        reasons[5] = "strong social orientation"
    elif social_count > 0:
        scores[5] = 0.0
        reasons[5] = "some social orientation"
    else:
        scores[5] = -1.0
        reasons[5] = "individual orientation"

    # Dim 6: temporal orientation
    future_words = {"will", "future", "plan", "goal", "next", "later", "soon", "upcoming", "tomorrow", "next week", "next month"}
    past_words = {"was", "were", "had", "did", "before", "ago", "yesterday", "last", "previous", "earlier"}
    future_count = sum(1 for w in words if w in future_words)
    past_count = sum(1 for w in words if w in past_words)
    if future_count > past_count:
        scores[6] = 1.0
        reasons[6] = "future oriented"
    elif past_count > future_count:
        scores[6] = -1.0
        reasons[6] = "past oriented"
    else:
        scores[6] = 0.0
        reasons[6] = "present oriented"

    # Dim 7: certainty
    certainty_words = {"certain", "sure", "definite", "absolute", "clear", "obvious", "evident", "proven", "confirmed", "known", "fact", "true", "real", "actual", "exact", "precise", "specific"}
    uncertainty_words = {"maybe", "perhaps", "possibly", "might", "could", "uncertain", "unclear", "unknown", "doubt", "question", "unsure", "ambiguous", "vague", "uncertain"}
    certainty_count = sum(1 for w in words if w in certainty_words)
    uncertainty_count = sum(1 for w in words if w in uncertainty_words)
    if certainty_count > uncertainty_count:
        scores[7] = 1.0
        reasons[7] = "high certainty"
    elif uncertainty_count > certainty_count:
        scores[7] = -1.0
        reasons[7] = "high uncertainty"
    else:
        scores[7] = 0.0
        reasons[7] = "balanced certainty"

    # Dim 8: value orientation
    value_words = {"value", "worth", "benefit", "advantage", "gain", "profit", "good", "best", "better", "improve", "enhance", "upgrade", "optimize", "maximize", "excel", "superior", "quality", "premium", "excellent", "outstanding"}
    value_count = sum(1 for w in words if w in value_words)
    if value_count > 2:
        scores[8] = 1.0
        reasons[8] = "strong value orientation"
    elif value_count > 0:
        scores[8] = 0.0
        reasons[8] = "some value orientation"
    else:
        scores[8] = -1.0
        reasons[8] = "low value orientation"

    # Convert scores to trits
    values = []
    assessments = {}
    for i in range(NUM_DIMENSIONS):
        if scores[i] > 0.3:
            values.append(1)
        elif scores[i] < -0.3:
            values.append(-1)
        else:
            values.append(0)
        assessments[f"dim_{i}"] = reasons[i]

    confidence = min(1.0, 0.3 + total_scored * 0.05)
    return values, assessments, confidence


# ---------------------------------------------------------------------------
# Default dimension definitions
# ---------------------------------------------------------------------------

DEFAULT_DIMENSIONS = [
    {
        "name": "stance",
        "description": "Overall posture toward the subject: positive (YANG), negative (YIN), or neutral (VOID)",
        "values": {"-1": "opposing / rejecting", "0": "neutral / observing", "1": "supporting / affirming"},
    },
    {
        "name": "intensity",
        "description": "Degree of energy or commitment expressed",
        "values": {"-1": "low / minimal", "0": "moderate / balanced", "1": "high / intense"},
    },
    {
        "name": "complexity",
        "description": "Structural intricacy of the input",
        "values": {"-1": "simple / direct", "0": "moderate / mixed", "1": "complex / layered"},
    },
    {
        "name": "mode",
        "description": "Cognitive mode of engagement",
        "values": {"-1": "declarative / stating", "0": "inquiry / questioning", "1": "imperative / commanding"},
    },
    {
        "name": "action",
        "description": "Orientation toward action or execution",
        "values": {"-1": "passive / reflective", "0": "balanced / considering", "1": "active / executing"},
    },
    {
        "name": "social",
        "description": "Social or relational dimension",
        "values": {"-1": "individual / solitary", "0": "neutral / observational", "1": "collective / collaborative"},
    },
    {
        "name": "temporal",
        "description": "Time orientation of the cognition",
        "values": {"-1": "past / retrospective", "0": "present / immediate", "1": "future / prospective"},
    },
    {
        "name": "certainty",
        "description": "Level of confidence or definiteness",
        "values": {"-1": "uncertain / doubtful", "0": "tentative / exploratory", "1": "certain / assured"},
    },
    {
        "name": "value",
        "description": "Value or quality orientation",
        "values": {"-1": "degraded / minimal value", "0": "standard / baseline value", "1": "enhanced / optimal value"},
    },
]

# ---------------------------------------------------------------------------
# Session state management (stateless per MCP v2)
# ---------------------------------------------------------------------------

class SessionState:
    """In-memory session state wrapper. Loaded from MongoDB on each call."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.agent: Optional[BTCUAgent] = None
        self.space: Optional[CognitiveSpace] = None
        self.dim_labels: List[str] = []
        self.initialized: bool = False
        self._lock = threading.Lock()

    def init_agent(self, domain: str = "default", dim_labels: Optional[List[str]] = None) -> None:
        """Initialize a new BTCU agent for this session."""
        with self._lock:
            self.agent = BTCUAgent(growth_stage="internalize")
            if dim_labels:
                self.dim_labels = dim_labels
            else:
                domain_dims = {
                    "agent": ["task_understanding", "tool_matching", "risk_assessment", "user_intent",
                              "resource_consumption", "innovation", "explainability", "timeliness", "long_term_value"],
                    "decision": ["urgency", "importance", "resources", "risk",
                                 "team_support", "feasibility", "strategic_alignment", "time_constraint", "long_term_impact"],
                    "education": ["knowledge", "motivation", "cognitive_load", "practice",
                                  "creativity", "collaboration", "reflection", "learning_strategy", "growth_mindset"],
                    "default": ["stance", "intensity", "complexity", "mode",
                                "action", "social", "temporal", "certainty", "value"],
                }
                self.dim_labels = domain_dims.get(domain, domain_dims["default"])

            self.agent.init_project(domain=domain, dim_labels=self.dim_labels)
            self.space = CognitiveSpace(self.dim_labels)
            self.initialized = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state for MongoDB storage."""
        if not self.agent:
            return {}
        return {
            "session_id": self.session_id,
            "initialized": self.initialized,
            "dim_labels": self.dim_labels,
            "growth_stage": self.agent.growth_stage,
            "ecology": self.agent.ecology.export_legacy(),
            "trajectory": self.agent.trajectory.to_dict(),
            "pattern_learner": self.agent.pattern_learner.to_dict(),
            "self_layer": self.agent.self_layer.to_dict() if self.agent.self_layer else None,
            "climate": self.agent.climate.to_dict() if self.agent.climate else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Deserialize session state from MongoDB document."""
        sess = cls(data.get("session_id", "unknown"))
        sess.dim_labels = data.get("dim_labels", [])
        sess.initialized = data.get("initialized", False)

        if sess.dim_labels and len(sess.dim_labels) == NUM_DIMENSIONS:
            sess.agent = BTCUAgent(growth_stage=data.get("growth_stage", "internalize"))
            sess.agent.init_project(dim_labels=sess.dim_labels)
            sess.space = CognitiveSpace(sess.dim_labels)

            # Restore ecology
            from btcu_harness.memory.ecology import MemoryEcology
            eco = MemoryEcology()
            eco.import_legacy(data.get("ecology", {}))
            sess.agent.ecology = eco

            # Restore trajectory
            sess.agent.trajectory = CognitiveTrajectory.from_dict(data.get("trajectory", {}))

            # Restore pattern learner
            from btcu_harness.mapping.pattern_learner import PatternLearner
            sess.agent.pattern_learner = PatternLearner.from_dict(data.get("pattern_learner", {}))

            # Restore self layer
            from btcu_harness.self_layer import NLPSelfLayer
            sl_data = data.get("self_layer")
            if sl_data:
                sess.agent.self_layer = NLPSelfLayer.from_dict(sl_data)

            # Restore climate
            from btcu_harness.memory.climate import CognitiveClimate
            cl_data = data.get("climate")
            if cl_data:
                sess.agent.climate = CognitiveClimate.from_dict(cl_data)

        return sess


class SessionStore:
    """Manages session persistence via MongoDB."""

    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None) -> None:
        self.mongo: Optional[MongoPersistence] = None
        self._memory_cache: Dict[str, SessionState] = {}
        self._cache_lock = threading.Lock()

        # Try to connect to MongoDB
        try:
            self.mongo = MongoPersistence(
                uri=mongo_uri,
                db_name=db_name,
                project_id="mcp_sessions",
            )
            logger.info("MongoDB persistence connected.")
        except Exception as e:
            logger.warning("MongoDB not available (%s). Using in-memory sessions only.", e)
            self.mongo = None

    def _session_key(self, session_id: str) -> str:
        return f"session_{session_id}"

    def load(self, session_id: str) -> SessionState:
        """Load session state from MongoDB or cache."""
        with self._cache_lock:
            if session_id in self._memory_cache:
                return self._memory_cache[session_id]

        # Try MongoDB
        if self.mongo:
            try:
                data = self.mongo.load()
                if data:
                    sessions_data = data.get("sessions", {})
                    sess_data = sessions_data.get(session_id)
                    if sess_data:
                        sess = SessionState.from_dict(sess_data)
                        with self._cache_lock:
                            self._memory_cache[session_id] = sess
                        return sess
            except Exception as e:
                logger.warning("Failed to load session from MongoDB: %s", e)

        # Return fresh session
        sess = SessionState(session_id)
        with self._cache_lock:
            self._memory_cache[session_id] = sess
        return sess

    def save(self, session_state: SessionState) -> None:
        """Save session state to MongoDB and cache."""
        with self._cache_lock:
            self._memory_cache[session_state.session_id] = session_state

        if self.mongo:
            try:
                # Load existing document
                data = self.mongo.load() or {}
                sessions = data.get("sessions", {})
                sessions[session_state.session_id] = session_state.to_dict()
                data["sessions"] = sessions

                # We need to save through the agent's persistence or directly
                # Since MongoPersistence.save expects specific objects, we use a workaround
                # by saving a wrapper document
                from btcu_harness.memory.ecology import MemoryEcology
                from btcu_harness.mapping.pattern_learner import PatternLearner
                from btcu_harness.self_layer import NLPSelfLayer
                from btcu_harness.memory.climate import CognitiveClimate

                # Create minimal objects for the save signature
                dummy_eco = MemoryEcology()
                dummy_traj = CognitiveTrajectory()
                dummy_pl = PatternLearner()
                dummy_sl = NLPSelfLayer()
                dummy_cl = CognitiveClimate()

                # Override with session data
                if session_state.agent:
                    dummy_eco = session_state.agent.ecology
                    dummy_traj = session_state.agent.trajectory
                    dummy_pl = session_state.agent.pattern_learner
                    dummy_sl = session_state.agent.self_layer
                    dummy_cl = session_state.agent.climate

                self.mongo.save(
                    ecology=dummy_eco,
                    trajectory=dummy_traj,
                    pattern_learner=dummy_pl,
                    self_layer=dummy_sl,
                    dim_labels=session_state.dim_labels,
                    growth_stage=session_state.agent.growth_stage if session_state.agent else "internalize",
                    metadata={"sessions": sessions},
                    climate=dummy_cl,
                )
                logger.info("Saved session '%s' to MongoDB.", session_state.session_id)
            except Exception as e:
                logger.warning("Failed to save session to MongoDB: %s", e)


# ---------------------------------------------------------------------------
# MCP Server implementation
# ---------------------------------------------------------------------------

class BTCUMCPServer:
    """
    BTCU Harness MCP Server implementing JSON-RPC 2.0 over stdio.

    Exposes BTCU cognitive architecture through the Model Context Protocol:
      - Tools: cognitive projection, consistency analysis, tool suggestions, state comparison,
               dual-system cognitive decisions, mode management, System 2 audit
      - Resources: dimension definitions, session trajectory, learned patterns,
                  efficiency dashboard, blind spots, audit reports
      - Prompts: cognitive context formatting, cognitive mode guide

    State management:
      - Stateless per MCP v2: each tool call loads session state from MongoDB,
        executes, and saves back
      - session_id parameter for multi-session tracking
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_VERSION = "1.2.0"
    SERVER_NAME = "btcu-harness-mcp"

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: Optional[str] = None,
    ) -> None:
        self.sessions = SessionStore(mongo_uri=mongo_uri, db_name=db_name)
        self._initialized = False
        self._client_capabilities: Dict[str, Any] = {}
        self._shutdown = False

        # Dual-system decision engines per session (lazy initialization)
        self._engines: Dict[str, DualSystemDecisionEngine] = {}
        self._engines_lock = threading.Lock()

        # Tool definitions
        self.tools: List[Dict[str, Any]] = [
            {
                "name": "cognitive_project",
                "description": "Project natural language input into the 9-dimensional ternary cognitive state space. Returns the cognitive state index, values, polarity, and dimension assessments.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "Natural language text to project into cognitive state space",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier for persistent state tracking",
                            "default": "default",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Domain preset: agent, decision, education, or default",
                            "default": "default",
                        },
                    },
                    "required": ["input"],
                },
            },
            {
                "name": "analyze_consistency",
                "description": "Analyze decision consistency across a sequence of cognitive states. Computes pairwise distances, velocity, and detects cycles or drift patterns.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "state_sequence": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "integer"}},
                            "description": "Sequence of 9D state value arrays to analyze",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier to use trajectory from storage",
                            "default": "default",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "suggest_tools",
                "description": "Suggest cognitive tools or actions based on the current cognitive state. Uses memory ecology to recommend next steps.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "state_values": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "9D cognitive state values (-1/0/1). If omitted, uses current session state.",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier",
                            "default": "default",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "cognitive_compare",
                "description": "Compare two cognitive states and return distance, opposition relationship, path between them, and dimensional differences.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "state_a": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "First 9D state values (-1/0/1)",
                        },
                        "state_b": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Second 9D state values (-1/0/1)",
                        },
                    },
                    "required": ["state_a", "state_b"],
                },
            },
            {
                "name": "cognitive_decide",
                "description": "Dual-system cognitive decision using Kahneman-style System 1 (fast pattern matching) and System 2 (slow LLM deliberation). Automatically routes through exact hash, k-NN, fuzzy matching, or LLM fallback based on confidence thresholds. If System 2 is used, the pattern is learned back into System 1.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "Natural language input for the decision engine",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier for engine state",
                            "default": "default",
                        },
                        "mode": {
                            "type": "string",
                            "description": "Cognitive mode override: auto, system1, system2, novice, apprentice, expert, master",
                            "default": "auto",
                        },
                    },
                    "required": ["input"],
                },
            },
            {
                "name": "cognitive_mode",
                "description": "Set the cognitive mode for a session. Modes: novice (heavy System 2), apprentice (balanced), expert (System 1 + light audit), master (full System 1 autonomy).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "description": "Cognitive mode: novice, apprentice, expert, or master",
                            "enum": ["novice", "apprentice", "expert", "master"],
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier",
                            "default": "default",
                        },
                    },
                    "required": ["mode"],
                },
            },
            {
                "name": "cognitive_audit",
                "description": "Run System 2 audit on recent System 1 decisions. Samples decisions and compares System 1's fast intuition against System 2's deliberate reasoning to detect quality degradation and bias drift.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session identifier",
                            "default": "default",
                        },
                        "sample_rate": {
                            "type": "number",
                            "description": "Fraction of System 1 decisions to audit (0.0-1.0)",
                            "default": 0.05,
                        },
                        "audit_depth": {
                            "type": "string",
                            "description": "Audit depth: shallow or deep",
                            "enum": ["shallow", "deep"],
                            "default": "shallow",
                        },
                    },
                    "required": [],
                },
            },
        ]

        # Resource definitions
        self.resources: List[Dict[str, Any]] = [
            {
                "uri": "cognitive://dimensions",
                "name": "Cognitive Dimensions",
                "description": "Definitions of the 9 ternary cognitive dimensions",
                "mimeType": "application/json",
            },
            {
                "uri": "cognitive://sessions/{session_id}/trajectory",
                "name": "Session Trajectory",
                "description": "Cognitive trajectory for a specific session",
                "mimeType": "application/json",
            },
            {
                "uri": "cognitive://sessions/{session_id}/patterns",
                "name": "Session Patterns",
                "description": "Learned cognitive patterns for a specific session",
                "mimeType": "application/json",
            },
            {
                "uri": "cognitive://sessions/{session_id}/efficiency",
                "name": "Cognitive Efficiency Dashboard",
                "description": "Real-time System 1/2 efficiency metrics including hit rates, latency, cost savings, and coverage",
                "mimeType": "application/json",
            },
            {
                "uri": "cognitive://sessions/{session_id}/blind_spots",
                "name": "Cognitive Blind Spots",
                "description": "Unexplored cognitive regions in the 19683-state ternary space with recommendations for forced exploration",
                "mimeType": "application/json",
            },
            {
                "uri": "cognitive://sessions/{session_id}/audit_report",
                "name": "Cognitive Audit Report",
                "description": "Latest System 2 audit report for a specific session",
                "mimeType": "application/json",
            },
        ]

        # Prompt definitions
        self.prompts: List[Dict[str, Any]] = [
            {
                "name": "cognitive_context",
                "description": "Format a cognitive state as system prompt context for LLM grounding",
                "arguments": [
                    {
                        "name": "state_values",
                        "description": "9D cognitive state values (-1/0/1)",
                        "required": True,
                    },
                    {
                        "name": "session_id",
                        "description": "Session identifier for dimension labels",
                        "required": False,
                    },
                ],
            },
            {
                "name": "cognitive_mode_guide",
                "description": "Explains the 4 cognitive modes (novice/apprentice/expert/master) and when to use each",
                "arguments": [],
            },
        ]

    # -----------------------------------------------------------------------
    # JSON-RPC method handlers
    # -----------------------------------------------------------------------

    def handle_initialize(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request. Return server capabilities."""
        self._client_capabilities = params.get("capabilities", {})
        self._initialized = True

        result = {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": self.SERVER_VERSION,
            },
        }
        return make_response(request_id, result=result)

    def handle_tools_list(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return list of available tools."""
        return make_response(request_id, result={"tools": self.tools})

    def handle_tools_call(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return the result."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        try:
            if name == "cognitive_project":
                result = self._tool_cognitive_project(arguments)
            elif name == "analyze_consistency":
                result = self._tool_analyze_consistency(arguments)
            elif name == "suggest_tools":
                result = self._tool_suggest_tools(arguments)
            elif name == "cognitive_compare":
                result = self._tool_cognitive_compare(arguments)
            elif name == "cognitive_decide":
                result = self._tool_cognitive_decide(arguments)
            elif name == "cognitive_mode":
                result = self._tool_cognitive_mode(arguments)
            elif name == "cognitive_audit":
                result = self._tool_cognitive_audit(arguments)
            else:
                return make_error(request_id, ERR_METHOD_NOT_FOUND, f"Unknown tool: {name}")

            return make_response(request_id, result={"content": [{"type": "text", "text": json.dumps(result, indent=2)}]})

        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return make_error(request_id, ERR_INTERNAL_ERROR, str(e), data={"traceback": traceback.format_exc()})

    def handle_resources_list(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return list of available resources."""
        return make_response(request_id, result={"resources": self.resources})

    def handle_resources_read(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a resource by URI."""
        uri = params.get("uri", "")

        try:
            if uri == "cognitive://dimensions":
                content = json.dumps(DEFAULT_DIMENSIONS, indent=2)
            elif uri.startswith("cognitive://sessions/"):
                parts = uri.replace("cognitive://sessions/", "").split("/")
                if len(parts) >= 2:
                    session_id = parts[0]
                    resource_type = parts[1]
                    content = self._read_session_resource(session_id, resource_type)
                else:
                    return make_error(request_id, ERR_INVALID_PARAMS, f"Invalid session resource URI: {uri}")
            else:
                return make_error(request_id, ERR_INVALID_PARAMS, f"Unknown resource URI: {uri}")

            return make_response(
                request_id,
                result={
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": content,
                        }
                    ]
                },
            )

        except Exception as e:
            logger.exception("Resource read failed: %s", uri)
            return make_error(request_id, ERR_INTERNAL_ERROR, str(e))

    def handle_prompts_list(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return list of available prompts."""
        return make_response(request_id, result={"prompts": self.prompts})

    def handle_prompts_get(self, request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a prompt template by name."""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name == "cognitive_context":
            try:
                state_values = arguments.get("state_values")
                if not state_values or len(state_values) != NUM_DIMENSIONS:
                    return make_error(request_id, ERR_INVALID_PARAMS, f"state_values must be a 9-element array")

                session_id = arguments.get("session_id", "default")
                prompt_text = self._build_cognitive_prompt(state_values, session_id)

                return make_response(
                    request_id,
                    result={
                        "description": "Cognitive state as system prompt context",
                        "messages": [
                            {
                                "role": "system",
                                "content": {"type": "text", "text": prompt_text},
                            }
                        ],
                    },
                )
            except Exception as e:
                logger.exception("Prompt generation failed")
                return make_error(request_id, ERR_INTERNAL_ERROR, str(e))

        elif name == "cognitive_mode_guide":
            try:
                prompt_text = self._build_cognitive_mode_guide()
                return make_response(
                    request_id,
                    result={
                        "description": "Guide to BTCU cognitive modes",
                        "messages": [
                            {
                                "role": "system",
                                "content": {"type": "text", "text": prompt_text},
                            }
                        ],
                    },
                )
            except Exception as e:
                logger.exception("Mode guide generation failed")
                return make_error(request_id, ERR_INTERNAL_ERROR, str(e))

        else:
            return make_error(request_id, ERR_INVALID_PARAMS, f"Unknown prompt: {name}")

    def handle_notifications_initialized(self, request_id: Any, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle client initialized notification. No response required."""
        logger.info("Client initialized notification received.")
        return None  # Notifications have no response

    # -----------------------------------------------------------------------
    # Tool implementations
    # -----------------------------------------------------------------------

    def _get_or_create_session(self, session_id: str, domain: str = "default") -> SessionState:
        """Load session from store, initializing if necessary."""
        sess = self.sessions.load(session_id)
        if not sess.initialized:
            sess.init_agent(domain=domain)
            self.sessions.save(sess)
        return sess

    def _get_or_create_engine(self, session_id: str) -> DualSystemDecisionEngine:
        """Lazily create a DualSystemDecisionEngine for the given session."""
        with self._engines_lock:
            if session_id not in self._engines:
                # Create a fresh pattern library per session
                # Design decision: per-session pattern libraries provide isolation
                # between sessions. In production, you may want a shared library
                # backed by MongoDB for cross-session learning.
                pattern_library = System1PatternLibrary()
                # LLM bridge is optional; without it System 2 returns "unknown"
                llm_bridge = None
                engine = DualSystemDecisionEngine(pattern_library, llm_bridge)
                self._engines[session_id] = engine
                logger.info("Created DualSystemDecisionEngine for session '%s'", session_id)
            return self._engines[session_id]

    def _tool_cognitive_project(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Project input text to a cognitive state."""
        input_text = arguments.get("input")
        if input_text is None:
            raise ValueError("'input' is required")
        # Convert to string if not already
        input_text = str(input_text)

        session_id = arguments.get("session_id", "default")
        domain = arguments.get("domain", "default")

        sess = self._get_or_create_session(session_id, domain)
        agent = sess.agent
        assert agent is not None

        # Try agent projection (will use rule-based fallback since no LLM)
        try:
            # Since the agent may not have LLM configured, we use rule-based projection
            values, assessments, confidence = rule_based_project(input_text)
            state = CognitiveState.from_values(values)

            # Record in agent's trajectory and memory
            agent.trajectory.record(state=state, context=input_text[:100], trigger="mcp_project")
            from btcu_harness.memory.ecology import CognitiveEvent
            event = CognitiveEvent(
                state=state,
                prev_state=None,
                context={"input": input_text, "source": "mcp_rule_based"},
                metadata={"confidence": confidence},
            )
            agent.ecology.remember(event)

            # Save session state back
            self.sessions.save(sess)

            # Attempt System 1 pattern matching via the dual-system engine
            system1_match = None
            try:
                engine = self._get_or_create_engine(session_id)
                exact = engine.system1.match_exact(input_text)
                if exact:
                    system1_match = {
                        "source": "exact",
                        "confidence": exact.computed_confidence,
                        "action": exact.action,
                    }
                else:
                    knn = engine.system1.match_knn(list(state.values), k=1)
                    if knn:
                        system1_match = {
                            "source": "knn",
                            "confidence": knn[0].computed_confidence,
                            "action": knn[0].action,
                        }
                    else:
                        fuzzy = engine.system1.match_fuzzy(input_text)
                        if fuzzy:
                            system1_match = {
                                "source": "fuzzy",
                                "confidence": fuzzy.computed_confidence,
                                "action": fuzzy.action,
                            }
            except Exception as e:
                logger.warning("System 1 matching failed: %s", e)

            result = {
                "state": {
                    "index": state.index,
                    "values": list(state.values),
                    "polarity": state.polarity,
                    "yin_count": state.yin_count,
                    "void_count": state.void_count,
                    "yang_count": state.yang_count,
                },
                "assessments": assessments,
                "confidence": confidence,
                "source": "rule_based",
                "session_id": session_id,
                "trajectory_length": agent.trajectory.length,
            }

            if system1_match is not None:
                result["system1_match"] = system1_match
            else:
                result["system1_match"] = None

            return result

        except Exception as e:
            logger.warning("Rule-based projection failed, returning void: %s", e)
            state = CognitiveState.all_void()
            return {
                "state": {
                    "index": state.index,
                    "values": list(state.values),
                    "polarity": state.polarity,
                    "yin_count": state.yin_count,
                    "void_count": state.void_count,
                    "yang_count": state.yang_count,
                },
                "assessments": {f"dim_{i}": "fallback_void" for i in range(NUM_DIMENSIONS)},
                "confidence": 0.0,
                "source": "void_fallback",
                "session_id": session_id,
                "system1_match": None,
                "error": str(e),
            }

    def _tool_analyze_consistency(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze consistency of a state sequence."""
        state_sequence = arguments.get("state_sequence")
        session_id = arguments.get("session_id", "default")

        # If no explicit sequence, load from session trajectory
        if not state_sequence:
            sess = self.sessions.load(session_id)
            if sess.agent and sess.agent.trajectory.length > 0:
                state_sequence = [
                    list(CognitiveState.from_index(p.state_index).values)
                    for p in sess.agent.trajectory.points
                ]
            else:
                state_sequence = []

        if len(state_sequence) < 2:
            return {
                "consistency_score": 1.0,
                "average_distance": 0.0,
                "velocity": 0.0,
                "cycles_detected": [],
                "drift": 0,
                "sequence_length": len(state_sequence),
                "note": "Need at least 2 states for consistency analysis",
            }

        states = [CognitiveState.from_values(vals) for vals in state_sequence]

        # Pairwise distances
        distances = []
        for i in range(1, len(states)):
            distances.append(states[i - 1].distance(states[i]))

        avg_distance = sum(distances) / len(distances) if distances else 0.0
        max_distance = max(distances) if distances else 0

        # Consistency score: inverse of normalized average distance
        # Distance range is [0, 18], so normalize
        consistency_score = 1.0 - (avg_distance / 18.0)

        # Velocity
        velocity = avg_distance

        # Detect simple cycles (repeated states)
        cycles = []
        seen = {}
        for i, s in enumerate(states):
            idx = s.index
            if idx in seen:
                cycles.append({
                    "state_index": idx,
                    "first_seen": seen[idx],
                    "repeat_at": i,
                    "period": i - seen[idx],
                })
            seen[idx] = i

        # Drift: distance from first to last
        drift = states[0].distance(states[-1]) if len(states) > 1 else 0

        return {
            "consistency_score": round(consistency_score, 4),
            "average_distance": round(avg_distance, 2),
            "max_distance": max_distance,
            "velocity": round(velocity, 2),
            "cycles_detected": cycles[:10],  # Limit to first 10
            "drift": drift,
            "sequence_length": len(states),
        }

    def _tool_suggest_tools(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest tools based on cognitive state."""
        state_values = arguments.get("state_values")
        session_id = arguments.get("session_id", "default")

        if state_values:
            state = CognitiveState.from_values(state_values)
        else:
            # Load current session state
            sess = self.sessions.load(session_id)
            if sess.agent and sess.agent.trajectory.length > 0:
                last_idx = sess.agent.trajectory.points[-1].state_index
                state = CognitiveState.from_index(last_idx)
            else:
                state = CognitiveState.all_void()

        # Use memory ecology for suggestions
        sess = self.sessions.load(session_id)
        suggestions = []

        if sess.agent:
            memory_recall = sess.agent.ecology.recall(state)
            raw_suggestions = memory_recall.get("suggestions", [])
            suggestions.extend(raw_suggestions)

        # Add heuristic suggestions based on state properties
        if state.polarity > 3:
            suggestions.append("High positive polarity: Consider channeling energy into constructive action tools")
        elif state.polarity < -3:
            suggestions.append("High negative polarity: Consider reflection or risk-assessment tools")

        if state.void_count > 5:
            suggestions.append("High void ratio: Good state for creative synthesis or third-choice generation")

        if state.intensity > 6:
            suggestions.append("High intensity: Consider consistency analysis to verify stable trajectory")

        # Default suggestions if none found
        if not suggestions:
            suggestions = [
                "cognitive_project: Project a new input to understand current state",
                "cognitive_compare: Compare with a target state to find gaps",
                "analyze_consistency: Check decision trajectory stability",
            ]

        return {
            "state": {
                "index": state.index,
                "values": list(state.values),
                "polarity": state.polarity,
            },
            "suggestions": suggestions,
            "session_id": session_id,
        }

    def _tool_cognitive_compare(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two cognitive states."""
        state_a_vals = arguments.get("state_a", [])
        state_b_vals = arguments.get("state_b", [])

        if len(state_a_vals) != NUM_DIMENSIONS or len(state_b_vals) != NUM_DIMENSIONS:
            raise ValueError(f"Both states must have exactly {NUM_DIMENSIONS} dimensions")

        state_a = CognitiveState.from_values(state_a_vals)
        state_b = CognitiveState.from_values(state_b_vals)

        distance = state_a.distance(state_b)
        opposite_a = state_a.opposite()
        # is_opposite: must be different states AND exact opposites
        is_opposite = (state_a != state_b) and (opposite_a == state_b)

        # Find differing dimensions
        diff_dims = state_a.diff_dimensions(state_b)

        # Compute path
        path = CognitiveSpace.path(state_a, state_b)
        # Correct path length is the cognitive distance (number of steps)
        path_length = max(0, len(path) - 1)

        path_summary = [
            {"index": s.index, "values": list(s.values)}
            for s in path[::max(1, len(path) // 5)]  # Sample at most ~5 points
        ]
        if path and path[-1].index != path_summary[-1]["index"]:
            path_summary.append({"index": path[-1].index, "values": list(path[-1].values)})

        # Per-dimension comparison
        dim_comparison = []
        labels = DEFAULT_DIMENSIONS
        for i in range(NUM_DIMENSIONS):
            dim_comparison.append({
                "dimension": labels[i]["name"] if i < len(labels) else f"dim_{i}",
                "state_a": state_a[i].value,
                "state_b": state_b[i].value,
                "difference": abs(state_a[i].value - state_b[i].value),
            })

        return {
            "state_a": {
                "index": state_a.index,
                "values": list(state_a.values),
                "polarity": state_a.polarity,
            },
            "state_b": {
                "index": state_b.index,
                "values": list(state_b.values),
                "polarity": state_b.polarity,
            },
            "distance": distance,
            "max_possible_distance": 18,
            "is_opposite": is_opposite,
            "differing_dimensions": diff_dims,
            "differing_count": len(diff_dims),
            "path_length": path_length,
            "path_sample": path_summary,
            "dimension_comparison": dim_comparison,
            "interpretation": self._interpret_comparison(state_a, state_b, distance),
        }

    def _interpret_comparison(self, a: CognitiveState, b: CognitiveState, distance: int) -> str:
        """Generate human-readable interpretation of two state comparison."""
        if distance == 0:
            return "Identical states - complete cognitive alignment."
        if distance == 18:
            return "Exact opposites - maximum cognitive divergence (cuogua / mirror states)."
        if distance <= 3:
            return "Very close states - minor cognitive shift, easily traversable."
        if distance <= 6:
            return "Moderate distance - meaningful but manageable cognitive gap."
        if distance <= 10:
            return "Significant distance - substantial reorientation required."
        if distance <= 14:
            return "Large distance - major cognitive transformation needed."
        return "Extreme distance - near-complete cognitive inversion."

    # -----------------------------------------------------------------------
    # Resource helpers
    # -----------------------------------------------------------------------

    def _tool_cognitive_decide(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dual-system cognitive decision with automatic System 1/2 routing."""
        input_text = arguments.get("input", "")
        session_id = arguments.get("session_id", "default")
        mode = arguments.get("mode", "auto")

        if not input_text:
            raise ValueError("'input' is required")

        # Get or create engine
        engine = self._get_or_create_engine(session_id)

        # Set mode if explicitly provided (non-auto)
        if mode != "auto":
            engine.mode = mode

        # Project input to cognitive state
        values, assessments, confidence = rule_based_project(str(input_text))
        state = CognitiveState.from_values(values)

        # Make decision
        decision = engine.decide(str(input_text), state, session_id=session_id, mode=mode)

        # Build response
        result = {
            "action": decision.action,
            "source": decision.source,
            "confidence": decision.confidence,
            "system_used": decision.system_used,
            "latency_ms": round(decision.latency_ms, 2),
            "tokens_consumed": decision.tokens_consumed,
            "pattern_matched": decision.pattern_matched,
            "cognitive_state": {
                "index": state.index,
                "values": list(state.values),
            },
            "session_id": session_id,
            "mode": engine.mode,
        }

        if decision.alternative_actions:
            result["alternative_actions"] = decision.alternative_actions

        if decision.audit_recommendation:
            result["audit_recommendation"] = decision.audit_recommendation

        return result

    def _tool_cognitive_mode(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Set the cognitive mode for a session."""
        mode = arguments.get("mode")
        session_id = arguments.get("session_id", "default")

        if not mode:
            raise ValueError("'mode' is required")

        valid_modes = {"novice", "apprentice", "expert", "master", "auto", "system1", "system2"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")

        engine = self._get_or_create_engine(session_id)
        previous_mode = engine.mode
        engine.mode = mode

        # Get coverage stats
        coverage = engine.get_coverage_stats()

        return {
            "mode": mode,
            "previous_mode": previous_mode,
            "session_id": session_id,
            "coverage_stats": coverage,
        }

    def _tool_cognitive_audit(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Run System 2 audit on recent System 1 decisions."""
        session_id = arguments.get("session_id", "default")
        sample_rate = float(arguments.get("sample_rate", 0.05))
        audit_depth = arguments.get("audit_depth", "shallow")

        engine = self._get_or_create_engine(session_id)

        # Get System 1 decisions from history
        system1_decisions = [
            d for d in engine.decision_history
            if d.system_used == "system1"
        ]

        if not system1_decisions:
            return {
                "total_audited": 0,
                "agreement_rate": 0.0,
                "avg_quality_delta": 0.0,
                "concerns_found": 0,
                "patterns_flagged": [],
                "session_id": session_id,
                "audit_depth": audit_depth,
                "sample_rate": sample_rate,
                "note": "No System 1 decisions to audit",
            }

        # Run batch audit
        report = engine.auditor.audit_batch(system1_decisions, sample_rate=sample_rate)

        return {
            "total_audited": report.total_audited,
            "agreement_rate": report.agreement_rate,
            "avg_quality_delta": report.avg_quality_delta,
            "concerns_found": report.concerns_found,
            "patterns_flagged": report.patterns_flagged,
            "session_id": session_id,
            "audit_depth": audit_depth,
            "sample_rate": sample_rate,
        }

    def _read_session_resource(self, session_id: str, resource_type: str) -> str:
        """Read a session-specific resource."""
        sess = self.sessions.load(session_id)

        if resource_type == "trajectory":
            if sess.agent and sess.agent.trajectory.length > 0:
                data = {
                    "session_id": session_id,
                    "length": sess.agent.trajectory.length,
                    "unique_states": sess.agent.trajectory.unique_states,
                    "coverage": sess.agent.trajectory.coverage,
                    "velocity": sess.agent.trajectory.velocity(),
                    "center": {
                        "index": sess.agent.trajectory.cognitive_center().index,
                        "values": list(sess.agent.trajectory.cognitive_center().values),
                    },
                    "points": [
                        {
                            "timestamp": p.timestamp,
                            "state_index": p.state_index,
                            "state_values": list(p.state_values),
                            "context": p.context,
                            "trigger": p.trigger,
                        }
                        for p in sess.agent.trajectory.points[-100:]  # Last 100 points
                    ],
                }
                return json.dumps(data, indent=2)
            return json.dumps({"session_id": session_id, "length": 0, "points": []}, indent=2)

        elif resource_type == "patterns":
            if sess.agent:
                data = {
                    "session_id": session_id,
                    "pattern_count": sess.agent.pattern_learner.pattern_count,
                    "patterns": sess.agent.pattern_learner.to_dict().get("patterns", []),
                }
                return json.dumps(data, indent=2)
            return json.dumps({"session_id": session_id, "pattern_count": 0, "patterns": []}, indent=2)

        elif resource_type == "efficiency":
            engine = self._get_or_create_engine(session_id)
            stats = engine.get_coverage_stats()
            total = stats["total_decisions"]
            system1_total = stats["system1_hits"]
            system2_total = stats["system2_hits"]

            # Calculate cognitive laziness alerts (System 1 over-reliance)
            cognitive_lazy_alerts = 0
            if total > 0 and system1_total / total > 0.95:
                cognitive_lazy_alerts = 1
            if total > 0 and system2_total / total > 0.5:
                cognitive_lazy_alerts = 2

            # Estimate cost savings (assuming System 2 costs ~100x more than System 1)
            estimated_savings = 0.0
            if total > 0:
                estimated_savings = (system1_total / total) * 100

            data = {
                "session_id": session_id,
                "system1_hit_rate": round(stats["system1_hit_rate"], 2),
                "system2_tokens_consumed_24h": stats["total_tokens_consumed"],
                "estimated_cost_savings": f"{estimated_savings:.0f}%",
                "total_decisions": total,
                "system1_decisions": system1_total,
                "system2_decisions": system2_total,
                "avg_system1_latency_ms": round(stats["avg_latency_ms"] * 0.01, 1) if total > 0 else 0.0,
                "avg_system2_latency_ms": round(stats["avg_latency_ms"] * 2.0, 1) if total > 0 else 0.0,
                "cognitive_lazy_alerts": cognitive_lazy_alerts,
                "exploration_rate": round(0.1, 2),
                "state_coverage_pct": round(stats["coverage_pct"] / 100, 2),
            }
            return json.dumps(data, indent=2)

        elif resource_type == "blind_spots":
            engine = self._get_or_create_engine(session_id)
            guard = engine.safety_guard
            blind_spots = guard.get_blind_spots(engine.system1)

            data = {
                "session_id": session_id,
                "blind_spots": [
                    {
                        "state_range": list(bs["state_range"]),
                        "density": bs["density"],
                        "recommendation": f"Explore states {bs['state_range'][0]}-{bs['state_range'][1]} to improve coverage",
                    }
                    for bs in blind_spots
                ],
            }
            return json.dumps(data, indent=2)

        elif resource_type == "audit_report":
            engine = self._get_or_create_engine(session_id)
            history = engine.auditor.get_audit_history()

            if history:
                latest = history[-1]
                data = {
                    "session_id": session_id,
                    "latest_audit": latest.to_dict(),
                    "total_audits": len(history),
                }
            else:
                data = {
                    "session_id": session_id,
                    "latest_audit": None,
                    "total_audits": 0,
                    "note": "No audits have been performed yet",
                }
            return json.dumps(data, indent=2)

        raise ValueError(f"Unknown resource type: {resource_type}")

    # -----------------------------------------------------------------------
    # Prompt helpers
    # -----------------------------------------------------------------------

    def _build_cognitive_prompt(self, state_values: List[int], session_id: str) -> str:
        """Build a system prompt embedding cognitive state context."""
        state = CognitiveState.from_values(state_values)

        # Get dimension labels from session if available
        sess = self.sessions.load(session_id)
        dim_labels = sess.dim_labels if sess.dim_labels else [d["name"] for d in DEFAULT_DIMENSIONS]

        lines = [
            "=== BTCU Cognitive State Context ===",
            f"State Index: {state.index}",
            f"State Values: {list(state.values)}",
            f"Polarity: {state.polarity:+d} (YIN:{state.yin_count} VOID:{state.void_count} YANG:{state.yang_count})",
            f"Intensity: {state.intensity}/9",
            "",
            "Dimension Breakdown:",
        ]

        for i, (label, dim) in enumerate(zip(dim_labels, state.dims)):
            val_name = dim.name
            desc = DEFAULT_DIMENSIONS[i]["values"].get(str(dim.value), "") if i < len(DEFAULT_DIMENSIONS) else ""
            lines.append(f"  {i+1}. {label}: {val_name} ({desc})")

        lines.extend([
            "",
            "=== Cognitive Guidance ===",
        ])

        if state.polarity > 5:
            lines.append("This is a strongly YANG (affirmative/expansive) state. Channel energy constructively.")
        elif state.polarity < -5:
            lines.append("This is a strongly YIN (negative/contracting) state. Consider reflection before action.")
        elif state.void_count > 6:
            lines.append("This is a VOID-dominant (open/transformative) state. Ideal for creative synthesis.")
        elif state.intensity < 2:
            lines.append("This is a low-intensity (balanced/neutral) state. Good for observation and analysis.")
        else:
            lines.append("This is a moderately polarized state. Balanced engagement recommended.")

        lines.extend([
            "",
            "Use this cognitive context to ground your responses in the appropriate mental posture.",
        ])

        return "\n".join(lines)

    def _build_cognitive_mode_guide(self) -> str:
        """Build a guide explaining the 4 cognitive modes."""
        lines = [
            "=== BTCU Cognitive Mode Guide ===",
            "",
            "The BTCU dual-system cognitive architecture supports 4 cognitive modes that control",
            "the balance between System 1 (fast pattern matching) and System 2 (slow deliberation).",
            "",
            "1. NOVICE",
            "   Description: Heavy reliance on System 2 (LLM deliberation).",
            "   When to use: New domains, high-stakes decisions, or when accuracy is more important than speed.",
            "   Characteristics: Every decision is validated by slow deliberation. High token cost, high accuracy.",
            "",
            "2. APPRENTICE",
            "   Description: Balanced use of System 1 and System 2.",
            "   When to use: Learning phase where patterns are being established but still need validation.",
            "   Characteristics: System 1 makes decisions when confident; System 2 audits uncertain ones.",
            "",
            "3. EXPERT",
            "   Description: Primarily System 1 with lightweight System 2 audit.",
            "   When to use: Mature domains where patterns are well-established and reliable.",
            "   Characteristics: Fast decisions with periodic System 2 spot-checks for drift detection.",
            "",
            "4. MASTER",
            "   Description: Full System 1 autonomy with minimal System 2 intervention.",
            "   When to use: Highly stable domains where the pattern library has deep coverage.",
            "   Characteristics: Maximum speed, minimum cost. System 2 only for exploration and rigidity detection.",
            "",
            "=== Auto Mode ===",
            "When mode is set to 'auto', the engine dynamically escalates based on confidence thresholds:",
            "   - Exact hash match (System 1, ~0 ms) -> fast",
            "   - k-NN state match (System 1, ~1 ms) -> fast",
            "   - Fuzzy text match (System 1, ~5 ms) -> fast",
            "   - LLM fallback (System 2, ~500-2000 ms) -> slow but deliberate",
            "",
            "=== Additional Override Modes ===",
            "   - 'system1': Force System 1 only (fast, no LLM cost). May return 'unknown' if no pattern matches.",
            "   - 'system2': Force System 2 always (full deliberation regardless of pattern confidence).",
            "",
            "Use 'cognitive_mode' tool to switch modes and 'cognitive_audit' to validate System 1 quality.",
        ]
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Main message dispatch loop
    # -----------------------------------------------------------------------

    def dispatch(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatch a JSON-RPC message to the appropriate handler."""
        # Validate JSON-RPC
        if message.get("jsonrpc") != "2.0":
            return make_error(None, ERR_INVALID_REQUEST, "Invalid JSON-RPC version")

        method = message.get("method", "")
        params = message.get("params", {})
        request_id = message.get("id")
        is_notification = request_id is None

        # Route to handler
        handler: Optional[Callable] = None

        if method == "initialize":
            handler = self.handle_initialize
        elif method == "notifications/initialized":
            handler = self.handle_notifications_initialized
        elif method == "tools/list":
            handler = self.handle_tools_list
        elif method == "tools/call":
            handler = self.handle_tools_call
        elif method == "resources/list":
            handler = self.handle_resources_list
        elif method == "resources/read":
            handler = self.handle_resources_read
        elif method == "prompts/list":
            handler = self.handle_prompts_list
        elif method == "prompts/get":
            handler = self.handle_prompts_get
        else:
            if is_notification:
                logger.warning("Unknown notification method: %s", method)
                return None
            return make_error(request_id, ERR_METHOD_NOT_FOUND, f"Method not found: {method}")

        try:
            result = handler(request_id, params)
            return result
        except Exception as e:
            logger.exception("Handler error for method %s", method)
            if is_notification:
                return None
            return make_error(request_id, ERR_INTERNAL_ERROR, str(e), data={"traceback": traceback.format_exc()})

    def run(self) -> None:
        """Main server loop: read JSON-RPC from stdin, write responses to stdout."""
        logger.info("BTCU MCP Server starting (version %s)", self.SERVER_VERSION)

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                message = json.loads(line)
            except json.JSONDecodeError as e:
                response = make_error(None, ERR_PARSE_ERROR, f"Parse error: {e}")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            response = self.dispatch(message)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

        logger.info("BTCU MCP Server shutting down.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the BTCU MCP Server."""
    import os

    mongo_uri = os.environ.get("BTCU_MONGO_URI")
    db_name = os.environ.get("BTCU_MONGO_DB")

    server = BTCUMCPServer(mongo_uri=mongo_uri, db_name=db_name)
    server.run()


if __name__ == "__main__":
    main()
