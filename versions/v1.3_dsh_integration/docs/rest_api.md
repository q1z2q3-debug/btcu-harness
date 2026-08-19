# REST API Reference

BTCU Harness exposes its cognitive operations through a **FastAPI** REST interface.

## Getting Started

```bash
pip install "btcu-harness[api]"
uvicorn btcu_harness.api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` for interactive Swagger UI.

## OpenAPI

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/init` | POST | Initialize a new project |
| `/api/project` | POST | Process input through cognitive pipeline |
| `/api/status` | GET | Get agent status |
| `/api/seasons` | GET | List cognitive seasons |
| `/api/climate` | GET | Get cognitive climate report |
| `/api/save` | POST | Save cognitive state |
| `/api/load` | POST | Load cognitive state |
| `/api/explore` | GET | Explore a cognitive state |

## Examples

### Initialize a Project

```bash
curl -X POST http://localhost:8000/api/init \
  -H "Content-Type: application/json" \
  -d '{"domain": "agent", "name": "My Agent"}'
```

Response:

```json
{
  "status": "initialized",
  "domain": "agent",
  "dimensions": ["任务理解", "工具匹配", "风险评估", ...],
  "growth_stage": "school",
  "storage": "btcu_state.json"
}
```

### Process Input

```bash
curl -X POST http://localhost:8000/api/project \
  -H "Content-Type: application/json" \
  -d '{"input_text": "Should we prioritize speed?"}'
```

Response:

```json
{
  "input": "Should we prioritize speed?",
  "current_state": {
    "index": 16928,
    "values": [1, 1, 1, 1, 0, -1, 1, 0, 1],
    "polarity": 5,
    "yin_count": 1,
    "void_count": 2,
    "yang_count": 6
  },
  "projection": {
    "source": "llm",
    "confidence": 0.8
  },
  "suggestions": [],
  "growth_stage": "school",
  "self_alignment": 0.78,
  "trajectory_length": 1,
  "pattern_matched": false,
  "third_choice_count": 0
}
```

### Explore State #9841 (All-VOID)

```bash
curl "http://localhost:8000/api/explore?index=9841"
```

Response:

```json
{
  "index": 9841,
  "values": [0, 0, 0, 0, 0, 0, 0, 0, 0],
  "polarity": 0,
  "intensity": 0,
  "yin_count": 0,
  "void_count": 9,
  "yang_count": 0,
  "opposite_index": 9841,
  "neighbors": [
    {"index": 9840, "values": [-1, 0, 0, 0, 0, 0, 0, 0, 0]},
    ...
  ]
}
```

### Explore by Values

```bash
curl "http://localhost:8000/api/explore?values=1,0,-1,1,0,-1,1,0,-1"
```

### Save and Load

```bash
curl -X POST http://localhost:8000/api/save
# {"status": "saved", "path": "btcu_state.json"}

curl -X POST http://localhost:8000/api/load
# {"status": "loaded", "success": true}
```

### Status

```bash
curl http://localhost:8000/api/status
```

### Seasons and Climate

```bash
curl http://localhost:8000/api/seasons
# {"count": 0, "seasons": []}

curl http://localhost:8000/api/climate
# {"polarity_trend": 0.0, "exploration_phase": "stagnant", ...}
```

## Docker

```bash
docker compose up
```

The API will be available at `http://localhost:8000`.
