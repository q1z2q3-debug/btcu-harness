# API Reference — Storage

Two persistence backends for BTCU cognitive state.

## `PersistenceLayer` (JSON)

File-based persistence for local development.

```python
from btcu_harness.storage.persistence import PersistenceLayer

store = PersistenceLayer("btcu_state.json")

# Save everything
store.save(
    ecology=agent.ecology,
    trajectory=agent.trajectory,
    pattern_learner=agent.pattern_learner,
    self_layer=agent.self_layer,
    dim_labels=agent.dimension_set.labels,
    growth_stage=agent.growth_stage,
    climate=agent.climate,
)

# Load
data = store.load()
```

### Save Includes

- Memory ecology (state memories + transition memories)
- Cognitive trajectory
- Pattern learner
- Self layer
- Dimension labels
- Growth stage
- Climate snapshot

### Load Returns

`dict` or `None` (if file doesn't exist).

## `MongoPersistence` (MongoDB)

MongoDB backend for production use.

```python
from btcu_harness.storage.mongo_persistence import MongoPersistence

store = MongoPersistence(
    uri="mongodb://localhost:27017",
    db_name="btcu_harness",
    project_id="my-agent",
)

# Same save/load interface as PersistenceLayer
store.save(...)
data = store.load()
```

### MongoDB Advantages

| Feature | JSON | MongoDB |
|---|---|---|
| Concurrent access | No (file lock) | Yes |
| Multi-agent | No | Yes (project_id namespacing) |
| Querying | No | Yes (MongoDB queries) |
| Scalability | Single machine | Distributed |
| Atomic operations | No | Yes |

### Requirements

```bash
pip install "btcu-harness[mongo]"
```

### Environment Variables

```bash
BTCU_MONGO_URI=mongodb://localhost:27017
BTCU_MONGO_DB=btcu_harness
```

### Additional Methods

| Method | Description |
|---|---|
| `delete()` | Delete project state |
| `list_projects()` | List all projects with summary |
| `exists` | Property: whether state exists |
| `info()` | Human-readable summary string |
| `close()` | Close MongoDB connection |

### Project Namespacing

Each `project_id` has its own document in the `cognitive_states` collection:

```python
store_a = MongoPersistence(project_id="agent-1")
store_b = MongoPersistence(project_id="agent-2")

# Completely independent states
store_a.save(...)
store_b.save(...)
```

This enables multi-agent deployments where each agent maintains its own cognitive biography.
