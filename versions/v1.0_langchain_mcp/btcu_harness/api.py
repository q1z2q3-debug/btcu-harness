"""
BTCU Harness REST API: FastAPI wrapper for cognitive operations.

Endpoints:
    POST   /api/init        Initialize a new project
    POST   /api/project     Process an input through the cognitive pipeline
    GET    /api/status      Get agent status
    GET    /api/seasons     List cognitive seasons
    GET    /api/climate     Get cognitive climate report
    POST   /api/save        Save cognitive state
    POST   /api/load        Load cognitive state
    GET    /api/explore     Explore a state by index or values

Run:
    uvicorn btcu_harness.api:app --host 0.0.0.0 --port 8000
    # or
    btcu serve --port 8000
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("btcu_harness.api")

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
except ImportError:
    raise ImportError(
        "FastAPI not installed. Install with: pip install 'btcu-harness[api]'"
    )

from .agent import BTCUAgent
from .core.state import CognitiveState, SPACE_SIZE

app = FastAPI(
    title="BTCU Harness API",
    description="Balanced Ternary Cognitive Unit Harness - REST API",
    version="1.1.0",
    license_info={"name": "MIT"},
)

# In-memory agent registry (single-agent mode)
_agent: Optional[BTCUAgent] = None


def _get_agent() -> BTCUAgent:
    global _agent
    if _agent is None:
        raise HTTPException(status_code=400, detail="No project initialized. Call /api/init first.")
    return _agent


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class InitRequest(BaseModel):
    domain: str = Field("agent", description="Domain preset: agent, decision, education, or custom")
    name: str = Field("BTCU Agent", description="Project name")
    dims: Optional[str] = Field(None, description="Comma-separated dimension labels (required for custom domain)")
    mission: Optional[str] = Field(None, description="Optional mission statement")
    storage: Optional[str] = Field(None, description="Storage path (default: btcu_state.json)")
    growth_stage: str = Field("school", description="Growth stage: school, internalize, graduate")


class ProjectRequest(BaseModel):
    input_text: str = Field(..., description="Input text to process")
    target_state: Optional[List[int]] = Field(None, description="Target state values (9 trits, each -1/0/1)")
    conflict_state: Optional[List[int]] = Field(None, description="Conflict state values for third-choice synthesis")


class ExploreRequest(BaseModel):
    index: Optional[int] = Field(None, ge=0, le=SPACE_SIZE - 1, description="State index to explore")
    values: Optional[List[int]] = Field(None, description="State values to explore (9 trits)")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/init")
def init_project(req: InitRequest):
    """Initialize a new BTCU project."""
    global _agent

    domain_dims = {
        "agent": ["任务理解", "工具匹配", "风险评估", "用户意图",
                  "资源消耗", "创新程度", "可解释性", "时效性", "长期价值"],
        "decision": ["紧迫性", "重要性", "资源可用", "风险水平",
                     "团队支持", "技术可行", "战略对齐", "时间约束", "长期影响"],
        "education": ["知识掌握", "学习动力", "认知负荷", "实践能力",
                      "创新思维", "协作能力", "反思能力", "学习策略", "成长心态"],
    }

    if req.domain in domain_dims:
        dim_labels = domain_dims[req.domain]
    else:
        if not req.dims:
            raise HTTPException(status_code=400, detail="--dims required for custom domain")
        dim_labels = [d.strip() for d in req.dims.split(",")]
        if len(dim_labels) != 9:
            raise HTTPException(status_code=400, detail="Exactly 9 dimension labels required")

    _agent = BTCUAgent(
        growth_stage=req.growth_stage,
        storage_path=req.storage or "btcu_state.json",
    )
    _agent.init_project(domain=req.domain, dim_labels=dim_labels)

    if req.mission:
        _agent.set_self_level(
            name="mission",
            description=req.mission,
            state=CognitiveState.from_values([0] * 9),
            weight=1.0,
            stability=0.95,
        )

    _agent.save()

    return {
        "status": "initialized",
        "domain": req.domain,
        "dimensions": dim_labels,
        "growth_stage": req.growth_stage,
        "storage": req.storage or "btcu_state.json",
    }


@app.post("/api/project")
def process_input(req: ProjectRequest):
    """Process an input through the cognitive pipeline."""
    agent = _get_agent()

    target = None
    if req.target_state:
        if len(req.target_state) != 9:
            raise HTTPException(status_code=400, detail="target_state must have 9 values")
        target = CognitiveState.from_values(req.target_state)

    conflict = None
    if req.conflict_state:
        if len(req.conflict_state) != 9:
            raise HTTPException(status_code=400, detail="conflict_state must have 9 values")
        conflict = CognitiveState.from_values(req.conflict_state)

    try:
        response = agent.process(req.input_text, target_state=target, conflict_state=conflict)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "input": response.input_text,
        "current_state": {
            "index": response.current_state.index,
            "values": list(response.current_state.values),
            "polarity": response.current_state.polarity,
            "yin_count": response.current_state.yin_count,
            "void_count": response.current_state.void_count,
            "yang_count": response.current_state.yang_count,
        },
        "projection": {
            "source": response.projection.source,
            "confidence": response.projection.confidence,
        },
        "memory_recall": response.memory_recall,
        "suggestions": response.suggestions,
        "growth_stage": response.growth_stage,
        "self_alignment": response.self_alignment,
        "trajectory_length": response.trajectory_length,
        "pattern_matched": response.pattern_matched,
        "pattern_confidence": response.pattern_confidence,
        "third_choice_count": len(response.third_choice_candidates),
        "llm_advice": response.llm_advice,
    }


@app.get("/api/status")
def get_status():
    """Get the agent's current status."""
    agent = _get_agent()
    return agent.status()


@app.get("/api/seasons")
def get_seasons():
    """List cognitive seasons discovered from memory."""
    agent = _get_agent()
    seasons = agent.ecology.sense_making()
    return {
        "count": len(seasons),
        "seasons": [
            {
                "season_type": s.season_type,
                "description": s.description,
            }
            for s in seasons
        ],
    }


@app.get("/api/climate")
def get_climate():
    """Get the cognitive climate report."""
    agent = _get_agent()
    return agent.climate_report()


@app.post("/api/save")
def save_state():
    """Save the current cognitive state."""
    agent = _get_agent()
    path = agent.save()
    return {"status": "saved", "path": path}


@app.post("/api/load")
def load_state():
    """Load cognitive state from storage."""
    global _agent
    _agent = BTCUAgent()
    success = _agent.load()
    return {"status": "loaded" if success else "not_found", "success": success}


@app.get("/api/explore")
def explore_state(index: Optional[int] = None, values: Optional[str] = None):
    """Explore a cognitive state by index or values."""
    if index is not None:
        if index < 0 or index >= SPACE_SIZE:
            raise HTTPException(status_code=400, detail=f"Index must be in [0, {SPACE_SIZE - 1}]")
        state = CognitiveState.from_index(index)
    elif values is not None:
        vals = [int(v) for v in values.split(",")]
        if len(vals) != 9:
            raise HTTPException(status_code=400, detail="Exactly 9 values required")
        state = CognitiveState.from_values(vals)
    else:
        raise HTTPException(status_code=400, detail="Provide 'index' or 'values' parameter")

    neighbors = state.neighbors()
    return {
        "index": state.index,
        "values": list(state.values),
        "polarity": state.polarity,
        "intensity": state.intensity,
        "yin_count": state.yin_count,
        "void_count": state.void_count,
        "yang_count": state.yang_count,
        "opposite_index": SPACE_SIZE - 1 - state.index,
        "neighbors": [
            {"index": n.index, "values": list(n.values)} for n in neighbors
        ],
    }


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "1.1.0", "space_size": SPACE_SIZE}


@app.get("/")
def root():
    """Root endpoint with API info."""
    return {
        "name": "BTCU Harness API",
        "version": "1.1.0",
        "docs": "/docs",
        "endpoints": [
            "/api/init", "/api/project", "/api/status",
            "/api/seasons", "/api/climate", "/api/save",
            "/api/load", "/api/explore", "/api/health",
        ],
    }
