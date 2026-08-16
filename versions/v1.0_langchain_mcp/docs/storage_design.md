# BTCU Harness 存储架构设计说明

**文档版本：v1.0**
**关联代码：`storage/persistence.py`, `memory/ecology.py`, `memory/trajectory.py`, `memory/climate.py`, `mapping/pattern_learner.py`, `self_layer/__init__.py`**

---

## 1. 存储架构总览

BTCU Harness 的存储层负责将 Agent 的完整认知状态持久化到磁盘，并在下次启动时无损恢复。当前采用 JSON 单文件方案，未来规划迁移至 MongoDB 以支持全量 19683 状态空间的高效读写。

```
┌─────────────────────────────────────────────────┐
│                   BTCUAgent                      │
│  Ecology · Trajectory · Patterns · Self+Climate  │
│                      │                           │
│             ┌────────▼────────┐                  │
│             │ PersistenceLayer │                  │
│             │  (save/restore)  │                  │
│             └────────┬────────┘                  │
└──────────────────────┼──────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 ┌────────────┐ ┌────────────┐ ┌────────────┐
 │ JSON 文件  │ │ MongoDB    │ │ Redis 缓存 │
 │ (当前)     │ │ (未来)     │ │ (热路径)   │
 └────────────┘ └────────────┘ └────────────┘
```

---

## 2. 当前 JSON 持久化

### 2.1 PersistenceLayer 类

`PersistenceLayer`（`storage/persistence.py:25`）是当前唯一的存储后端，以单个 JSON 文件保存 Agent 的全部认知状态。

```python
class PersistenceLayer:
    def __init__(self, storage_path: str) -> None: ...

    def save(
        self,
        ecology: MemoryEcology,
        trajectory: CognitiveTrajectory,
        pattern_learner: PatternLearner,
        self_layer: Any,              # NLPSelfLayer
        dim_labels: list,
        growth_stage: str,
        metadata: Optional[Dict[str, Any]] = None,
        climate: Any = None,          # CognitiveClimate
    ) -> str:
        """将完整认知状态写入磁盘，返回文件路径。"""
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `ecology` | `MemoryEcology` | 记忆生态（状态记忆 + 转化记忆 + 共振网络） |
| `trajectory` | `CognitiveTrajectory` | 认知轨迹（全部访问点序列） |
| `pattern_learner` | `PatternLearner` | 能力记忆（已学会的投影模式） |
| `self_layer` | `NLPSelfLayer` | NLP 自我层（身份、价值观、吸引子） |
| `dim_labels` | `list[str]` | 九维标签（锁定维度语义） |
| `growth_stage` | `str` | 成长阶段（school / internalize / graduate） |
| `metadata` | `Optional[Dict]` | 附加元数据（项目名、会话 ID 等） |
| `climate` | `Optional[CognitiveClimate]` | 认知气候快照 |

### 2.2 JSON 文件结构

`save()` 方法将所有模块序列化为一个嵌套 JSON 对象，顶层包含十个字段：

```json
{
  "version": "0.3",
  "saved_at": "2026-08-15T10:30:00+00:00",
  "dimension_labels": ["技术深度", "用户体验", "创新性", "..."],
  "growth_stage": "internalize",
  "memory_ecology": {
    "state_memories": { "16928": { "visits": [...], "activation": 0.8 } },
    "transition_memories": { "9841-16928": { "records": [...] } },
    "resonance_links": { ... },
    "stats": { "visited_states": 127, "total_visits": 342 }
  },
  "trajectory": { "points": [ { "timestamp": "...", "state_index": 16928 } ] },
  "pattern_learner": { "patterns": [ { "features": {...}, "state_index": 16928 } ] },
  "self_layer": { "identity": { ... }, "values": [...], "attractor": { ... } },
  "climate": { "polarity_trend": 0.32, "exploration_phase": "expanding" },
  "metadata": { "project": "btcu_demo", "session_id": "v03_validation" }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | `str` | 存储格式版本号，当前为 `"0.3"` |
| `saved_at` | `str` | 保存时间（ISO 8601 UTC） |
| `dimension_labels` | `list[str]` | 九维语义标签 |
| `growth_stage` | `str` | 成长阶段 |
| `memory_ecology` | `dict` | 记忆生态导出数据（`ecology.export_legacy()`） |
| `trajectory` | `dict` | 轨迹数据（`trajectory.to_dict()`） |
| `pattern_learner` | `dict` | 模式学习器数据（`pattern_learner.to_dict()`） |
| `self_layer` | `dict \| null` | 自我层数据（`self_layer.to_dict()`） |
| `climate` | `dict \| null` | 气候快照（`climate.to_dict()`） |
| `metadata` | `dict` | 用户自定义元数据 |

### 2.3 恢复方法

`PersistenceLayer` 提供五个独立的恢复方法，各自从加载的 JSON 字典中重建对应对象：

```python
data = persistence.load()

ecology = persistence.restore_ecology(data)                    # MemoryEcology
trajectory = persistence.restore_trajectory(data)              # CognitiveTrajectory
pattern_learner = persistence.restore_pattern_learner(data)    # PatternLearner
self_layer = persistence.restore_self_layer(data)              # NLPSelfLayer
climate = persistence.restore_climate(data)                    # CognitiveClimate
```

| 方法 | 输入键 | 输出 | 缺失时默认行为 |
|------|--------|------|---------------|
| `restore_ecology` | `memory_ecology` | `MemoryEcology` | 空生态 |
| `restore_trajectory` | `trajectory` | `CognitiveTrajectory` | 空轨迹 |
| `restore_pattern_learner` | `pattern_learner` | `PatternLearner` | 空学习器 |
| `restore_self_layer` | `self_layer` | `NLPSelfLayer` | 默认自我层 |
| `restore_climate` | `climate` | `CognitiveClimate` | 默认气候 |

每个恢复方法内部调用对应类的 `from_dict()` 或 `import_legacy()` 反序列化方法，保证数据往返（round-trip）的一致性。

---

## 3. MongoDB 集合设计（未来）

当状态空间扩展到全量 19683 时，JSON 全量加载的 O(n) 开销将成为瓶颈。MongoDB 方案将认知状态拆分到六个集合，实现 O(1) 单点查询。

```
btcu_db
├── state_memories        # 19683 个状态记忆文档
├── transition_memories   # 状态间转化记忆
├── trajectories          # 认知轨迹点
├── patterns              # 已学会的投影模式
├── self_levels           # NLP 自我层
└── climate_snapshots     # 认知气候快照
```

### 3.1 集合 Schema 总表

**db.state_memories** — 索引 `state_index`（0-19682）

| 字段 | 类型 | 说明 |
|------|------|------|
| `state_index` | `int` | 状态编号 0-19682 |
| `visits` | `array[object]` | 访问记录列表（`VisitRecord` 数组） |
| `insights` | `array[str]` | 提炼洞见（去重） |
| `resonance_links` | `dict[int, float]` | 共振链接 `{other_index: strength}` |
| `activation` | `float` | 激活水平 |
| `last_visited` | `str \| null` | 最后访问时间 |
| `first_visited` | `str \| null` | 首次访问时间 |
| `suppressed_decisions` | `array[str]` | 被抑制的决策 |
| `updated_at` | `date` | 文档最后更新时间 |

**db.transition_memories** — 复合索引 `(from_index, to_index)`

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_index` | `int` | 源状态编号 |
| `to_index` | `int` | 目标状态编号 |
| `records` | `array[object]` | 转化记录列表（`TransitionRecord` 数组） |
| `activation` | `float` | 激活水平 |
| `last_traversed` | `str \| null` | 最后穿越时间 |
| `updated_at` | `date` | 文档最后更新时间 |

**db.trajectories** — 索引 `timestamp`（降序）

| 字段 | 类型 | 说明 |
|------|------|------|
| `timestamp` | `str` | ISO 8601 时间戳 |
| `state_index` | `int` | 状态编号 |
| `state_values` | `array[int]` | 九维快照 |
| `context` | `str` | 认知上下文 |
| `trigger` | `str` | 触发原因 |
| `metadata` | `dict` | 附加元数据 |

**db.patterns** — 索引 `state_index`

| 字段 | 类型 | 说明 |
|------|------|------|
| `features` | `dict[str, float]` | 提取的文本特征 |
| `state_values` | `array[int]` | 对应九维状态值 |
| `state_index` | `int` | 状态编号 |
| `input_text` | `str` | 原始输入文本 |
| `source` | `str` | 来源（llm / pattern / hybrid） |
| `confidence` | `float` | 置信度 |
| `use_count` | `int` | 被复用次数 |
| `success_count` | `int` | 成功次数 |
| `created_at` | `date` | 创建时间 |

**db.self_levels** — 索引 `name`（唯一）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 自我层名称（如 "identity", "values"） |
| `content` | `dict` | 自我层内容 |
| `updated_at` | `date` | 最后更新时间 |

**db.climate_snapshots** — 索引 `step`

| 字段 | 类型 | 说明 |
|------|------|------|
| `step` | `int` | 步骤编号 |
| `polarity_trend` | `float` | 极性趋势 |
| `polarity_volatility` | `float` | 极性波动 |
| `exploration_phase` | `str` | 探索阶段（expanding/consolidating/stagnant） |
| `climate_zones` | `array[dict]` | 活跃区域 |
| `drift_magnitude` | `float` | 漂移幅度 |
| `dominant_period` | `int` | 主导周期 |
| `rhythm_regularity` | `float` | 节律稳定性 |
| `timestamp` | `str` | 快照时间 |

---

## 4. 索引策略

| 集合 | 索引字段 | 索引类型 | 说明 |
|------|----------|----------|------|
| `state_memories` | `state_index` | 唯一索引 | 每个状态编号唯一对应一个文档 |
| `transition_memories` | `(from_index, to_index)` | 复合唯一索引 | 支持"从 A 到 B 的转化"查询 |
| `trajectories` | `timestamp` | 降序索引 | 按时间倒序查询最近轨迹 |
| `patterns` | `state_index` | 普通索引 | 按状态编号查找已学模式 |
| `self_levels` | `name` | 唯一索引 | 每个自我层名称唯一 |
| `climate_snapshots` | `step` | 普通索引 | 按步骤查找气候快照 |
| `state_memories` | `growth_stage` | 稀疏索引 | 仅索引已设置该字段的文档 |

**稀疏索引说明**：`growth_stage` 字段并非每个状态记忆文档都有值，稀疏索引跳过缺失该字段的文档，减少索引体积。

```python
db.state_memories.create_index("state_index", unique=True)
db.transition_memories.create_index(
    [("from_index", 1), ("to_index", 1)], unique=True, name="idx_from_to"
)
db.trajectories.create_index([("timestamp", -1)], name="idx_ts_desc")
db.patterns.create_index("state_index", name="idx_state")
db.self_levels.create_index("name", unique=True)
db.climate_snapshots.create_index("step", name="idx_step")
db.state_memories.create_index("growth_stage", sparse=True, name="idx_growth_sparse")
```

---

## 5. 数据一致性

### 5.1 当前实现（JSON 单文件）

| ACID 属性 | 实现方式 | 局限 |
|-----------|----------|------|
| 原子性 | `json.dump()` 一次性写入 | 无 WAL，写入中断可能损坏文件 |
| 一致性 | 所有模块在同一个 JSON 中同时保存 | 无法部分更新 |
| 隔离性 | 单 Agent 单文件，无并发 | 不支持多 Agent 同时写 |
| 持久性 | `fsync` 由操作系统管理 | 可通过 `os.fsync()` 强化 |

建议增强：先写临时文件再原子替换（`tempfile` + `shutil.move`），避免写入中断导致文件损坏。

### 5.2 未来 MongoDB 实现

| ACID 属性 | 实现方式 |
|-----------|----------|
| 原子性 | 文档级原子操作（单文档更新天然原子） |
| 一致性 | 多集合写入使用 MongoDB 事务（4.0+） |
| 隔离性 | 事务提供 snapshot 隔离级别 |
| 持久性 | MongoDB journal + replica set |

```python
def save_checkpoint_mongodb(client, ecology, trajectory, self_layer):
    """事务化保存认知状态检查点。"""
    db = client["btcu_db"]
    with client.start_session() as session:
        with session.start_transaction():
            for idx, mem in ecology.state_store.items():
                db.state_memories.update_one(
                    {"state_index": idx}, {"$set": mem.to_dict()},
                    upsert=True, session=session
                )
            db.trajectories.insert_one(
                trajectory.last_point.to_dict(), session=session
            )
            db.self_levels.update_one(
                {"name": "identity"}, {"$set": self_layer.identity_dict()},
                upsert=True, session=session
            )
```

### 5.3 备份策略

| 策略 | JSON 方案 | MongoDB 方案 |
|------|-----------|-------------|
| 定期快照 | 复制 JSON 文件到备份目录 | `mongodump` 定时导出 |
| 增量备份 | 不支持 | oplog 重放 |
| 恢复粒度 | 全文件恢复 | 按集合 / 按文档恢复 |
| 备份频率 | 每次 `save()` 后 | 每日全量 + 实时 oplog |

---

## 6. 存储适配器接口设计

### 6.1 StorageAdapter 抽象接口

为支持多种存储后端的平滑切换，定义统一的 `StorageAdapter` 抽象基类。上层 `PersistenceLayer` 通过适配器透明访问不同后端：

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class StorageAdapter(ABC):
    """存储适配器抽象接口，所有后端（JSON/MongoDB/Redis）均实现此接口。"""

    @abstractmethod
    def save_state_memory(self, state_index: int, data: dict) -> None:
        """保存单个状态记忆。"""

    @abstractmethod
    def load_state_memory(self, state_index: int) -> Optional[dict]:
        """加载单个状态记忆，不存在返回 None。"""

    @abstractmethod
    def save_transition_memory(self, from_index: int, to_index: int, data: dict) -> None:
        """保存单条转化记忆。"""

    @abstractmethod
    def load_transition_memory(self, from_index: int, to_index: int) -> Optional[dict]:
        """加载单条转化记忆。"""

    @abstractmethod
    def append_trajectory_point(self, point: dict) -> None:
        """追加一个轨迹点。"""

    @abstractmethod
    def load_trajectory(self, limit: Optional[int] = None) -> List[dict]:
        """加载轨迹，limit=None 加载全部。"""

    @abstractmethod
    def save_pattern(self, pattern: dict) -> None:
        """保存一个投影模式。"""

    @abstractmethod
    def load_patterns_by_state(self, state_index: int) -> List[dict]:
        """按状态编号加载模式。"""

    @abstractmethod
    def save_self_layer(self, name: str, data: dict) -> None:
        """保存自我层。"""

    @abstractmethod
    def load_self_layer(self, name: str) -> Optional[dict]:
        """加载自我层。"""

    @abstractmethod
    def save_climate_snapshot(self, step: int, data: dict) -> None:
        """保存气候快照。"""

    @abstractmethod
    def load_climate_snapshot(self, step: int) -> Optional[dict]:
        """加载气候快照。"""

    @abstractmethod
    def save_full_state(self, state: dict) -> None:
        """全量保存（JSON 后端兼容接口）。"""

    @abstractmethod
    def load_full_state(self) -> Optional[dict]:
        """全量加载（JSON 后端兼容接口）。"""
```

### 6.2 JSON 适配器

```python
import json
import os


class JSONStorageAdapter(StorageAdapter):
    """JSON 文件存储适配器——全量读写，适合 < 10000 状态。"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._cache: Optional[dict] = None

    def _load_all(self) -> dict:
        if self._cache is None:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            else:
                self._cache = {}
        return self._cache

    def _flush(self) -> None:
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def save_state_memory(self, state_index: int, data: dict) -> None:
        all_data = self._load_all()
        all_data.setdefault("state_memories", {})[str(state_index)] = data
        self._flush()

    def load_state_memory(self, state_index: int) -> Optional[dict]:
        return self._load_all().get("state_memories", {}).get(str(state_index))

    def save_full_state(self, state: dict) -> None:
        self._cache = state
        self._flush()

    def load_full_state(self) -> Optional[dict]:
        return self._load_all()

    # save_transition_memory / load_transition_memory 等方法
    # 均基于 _load_all() 读取 + _flush() 写入实现，结构相同
```

### 6.3 MongoDB 适配器

```python
from pymongo import ASCENDING, DESCENDING, MongoClient
from datetime import datetime


class MongoDBStorageAdapter(StorageAdapter):
    """MongoDB 存储适配器——O(1) 单点查询，适合全量 19683 状态。"""

    def __init__(self, uri: str, db_name: str = "btcu_db") -> None:
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.db.state_memories.create_index("state_index", unique=True)
        self.db.transition_memories.create_index(
            [("from_index", ASCENDING), ("to_index", ASCENDING)], unique=True)
        self.db.trajectories.create_index([("timestamp", DESCENDING)])
        self.db.patterns.create_index("state_index")
        self.db.self_levels.create_index("name", unique=True)
        self.db.climate_snapshots.create_index("step")

    def save_state_memory(self, state_index: int, data: dict) -> None:
        data["state_index"] = state_index
        data["updated_at"] = datetime.utcnow()
        self.db.state_memories.update_one(
            {"state_index": state_index}, {"$set": data}, upsert=True)

    def load_state_memory(self, state_index: int) -> Optional[dict]:
        doc = self.db.state_memories.find_one({"state_index": state_index})
        if doc:
            doc.pop("_id", None)
            return doc
        return None

    def append_trajectory_point(self, point: dict) -> None:
        self.db.trajectories.insert_one(point)

    def load_trajectory(self, limit: Optional[int] = None) -> List[dict]:
        cursor = self.db.trajectories.find().sort("timestamp", DESCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def save_pattern(self, pattern: dict) -> None:
        self.db.patterns.insert_one(pattern)

    def load_patterns_by_state(self, state_index: int) -> List[dict]:
        return list(self.db.patterns.find({"state_index": state_index}))

    # save/load_transition_memory, save/load_self_layer,
    # save/load_climate_snapshot, save/load_full_state 方法结构类似
```

### 6.4 Redis 缓存适配器

Redis 适配器不作为主存储，仅作为 MongoDB 的读缓存层（Cache-Aside 模式）：

```python
import redis
import json


class RedisCacheAdapter(StorageAdapter):
    """Redis 缓存适配器——热路径加速，不作为主存储。"""

    def __init__(self, host: str = "localhost", port: int = 6379) -> None:
        self.r = redis.Redis(host=host, port=port, decode_responses=True)

    def _key(self, prefix: str, *parts) -> str:
        return f"btcu:{prefix}:{':'.join(str(p) for p in parts)}"

    def save_state_memory(self, state_index: int, data: dict) -> None:
        self.r.set(self._key("state", state_index),
                   json.dumps(data, ensure_ascii=False), ex=3600)

    def load_state_memory(self, state_index: int) -> Optional[dict]:
        raw = self.r.get(self._key("state", state_index))
        return json.loads(raw) if raw else None

    def append_trajectory_point(self, point: dict) -> None:
        self.r.lpush(self._key("trajectory"),
                     json.dumps(point, ensure_ascii=False))
        self.r.ltrim(self._key("trajectory"), 0, 999)  # 保留最近 1000 条

    def load_trajectory(self, limit: Optional[int] = None) -> List[dict]:
        end = (limit - 1) if limit else -1
        return [json.loads(r) for r in self.r.lrange(self._key("trajectory"), 0, end)]

    # 缓存适配器不支持全量保存/加载
    def save_full_state(self, state: dict) -> None:
        raise NotImplementedError("Redis cache does not support full state")

    def load_full_state(self) -> Optional[dict]:
        raise NotImplementedError("Redis cache does not support full state")
```

### 6.5 适配器工厂与后端迁移

```python
def create_adapter(backend: str, **kwargs) -> StorageAdapter:
    """工厂函数：根据后端名称创建适配器。"""
    if backend == "json":
        return JSONStorageAdapter(kwargs["file_path"])
    elif backend == "mongodb":
        return MongoDBStorageAdapter(kwargs["uri"], kwargs.get("db_name", "btcu_db"))
    elif backend == "redis":
        return RedisCacheAdapter(kwargs.get("host", "localhost"), kwargs.get("port", 6379))
    raise ValueError(f"Unknown storage backend: {backend}")


def migrate_storage(source: StorageAdapter, target: StorageAdapter) -> None:
    """在存储后端之间迁移全部数据（如 JSON → MongoDB）。"""
    full = source.load_full_state()
    if full and "state_memories" in full:
        for idx_str, mem_data in full["state_memories"].items():
            target.save_state_memory(int(idx_str), mem_data)
    for point in full.get("trajectory", {}).get("points", []):
        target.append_trajectory_point(point)
    # 逐模块迁移模式、自我层、气候...
```

---

## 7. 性能分析

### 7.1 复杂度对比

| 操作 | JSON 适配器 | MongoDB 适配器 | Redis 缓存 |
|------|------------|---------------|------------|
| 加载单个状态 | O(n) 全量解析 | O(1) 索引查询 | O(1) 键值查询 |
| 保存单个状态 | O(n) 全量重写 | O(1) upsert | O(1) SET |
| 加载全部轨迹 | O(1) 已在内存 | O(m) 游标扫描 | O(m) LRANGE |
| 全量保存 | O(n) 一次写入 | O(n) 批量 upsert | 不支持 |
| 适用状态规模 | < 10000 | 全量 19683 | 热点子集 |

### 7.2 适用场景

| 场景 | 推荐后端 | 原因 |
|------|----------|------|
| 开发调试 | JSON | 人类可读，便于检查和手动修改 |
| 单 Agent 小规模 | JSON | 状态数 < 1000，加载开销可忽略 |
| 多 Agent 大规模 | MongoDB | 19683 状态需 O(1) 查询 |
| 实时热路径加速 | Redis + MongoDB | 缓存高频访问状态，降低 DB 压力 |
| 认知审计 / 回放 | MongoDB | 可按时间范围查询历史轨迹 |

### 7.3 懒加载策略

全量 19683 状态中，Agent 实际访问的通常只有几百个。懒加载策略仅在实际访问时从存储后端加载状态记忆：

```python
class LazyStateStore:
    """懒加载状态存储：仅在实际访问时从适配器加载。"""

    def __init__(self, adapter: StorageAdapter) -> None:
        self._adapter = adapter
        self._cache: Dict[int, Any] = {}

    def get(self, state_index: int):
        if state_index in self._cache:       # 内存缓存命中
            return self._cache[state_index]
        data = self._adapter.load_state_memory(state_index)  # 从后端加载
        mem = StateMemory.from_dict(data) if data else StateMemory(state_index)
        self._cache[state_index] = mem
        return mem
```

### 7.4 热状态缓存与多级架构

高频访问的状态（attractor 附近、最近访问的状态）缓存在内存 LRU 中，避免反复查询存储后端：

```
请求 → HotStateCache (内存 LRU, 256 条)
          ↓ miss
       LazyStateStore (懒加载层)
          ↓ miss
       StorageAdapter (JSON / MongoDB)
          ↓
       RedisCacheAdapter (分布式缓存, 可选)
```

---

## 8. 多项目隔离

当多个 BTCU Agent 实例同时运行时，每个项目拥有独立的 19683 状态空间，互不干扰。

**JSON 方案**：每个项目使用独立的 JSON 文件路径。

```python
agent_a = BTCUAgent(storage_path="./projects/alpha/cognitive.json")
agent_b = BTCUAgent(storage_path="./projects/beta/cognitive.json")
```

**MongoDB 方案**：每个项目使用独立的数据库，或共享数据库 + `project_id` 字段隔离。

```python
# 方案 A：独立数据库
db_alpha = client["btcu_alpha"]
db_beta = client["btcu_beta"]

# 方案 B：共享数据库 + project_id 复合索引
db.state_memories.create_index(
    [("project_id", 1), ("state_index", 1)], unique=True
)
```

| 隔离规则 | 说明 |
|----------|------|
| 状态空间隔离 | 每个项目的 19683 状态空间完全独立 |
| 轨迹隔离 | 不同项目的认知轨迹不可交叉查询 |
| 模式隔离 | 项目 A 学到的模式不可被项目 B 直接复用 |
| 自我层隔离 | 每个项目有独立的身份和价值观 |
| 共享气候（可选） | 多个项目可共享气候模型以进行跨项目比较 |

---

## 9. 扩展点总表

| 扩展点 | 接口 / 机制 | 当前状态 | 未来规划 |
|--------|------------|----------|----------|
| JSON 适配器 | `JSONStorageAdapter` | 已实现（`PersistenceLayer`） | 抽象为独立适配器 |
| MongoDB 适配器 | `MongoDBStorageAdapter` | 未实现 | 按本文档 Schema 设计 |
| Redis 缓存适配器 | `RedisCacheAdapter` | 未实现 | Cache-Aside 模式 |
| 后端迁移 | `migrate_storage()` | 未实现 | JSON → MongoDB 一键迁移 |
| 懒加载 | `LazyStateStore` | 未实现 | 按需加载访问过的状态 |
| 热状态缓存 | `HotStateCache` | 未实现 | LRU 256 条内存缓存 |
| 多项目隔离 | 独立文件 / 独立 DB | JSON 文件隔离已实现 | MongoDB 多 DB 隔离 |
| 增量保存 | 差异检测 + 部分更新 | 未实现 | MongoDB upsert 逐文档更新 |
| 版本迁移 | `version` 字段 + 迁移函数 | 版本号 `"0.3"` | 版本升级时自动迁移旧格式 |

---

## 参考文献

1. MongoDB Documentation. (2024). *Transactions*. MongoDB 4.0+ multi-document ACID transactions.
2. Redis Documentation. (2024). *Cache Pattern — Cache-Aside*. Redis 最佳实践.
3. Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed Systems* (3rd ed.). 分布式存储一致性模型.
4. Gilbert, S., & Lynch, N. (2002). Brewer's conjecture and the feasibility of consistent, available, partition-tolerant web services. *ACM SIGACT News*. CAP 定理.
5. O'Neil, P., et al. (1996). *The Log-Structured Merge-Tree (LSM-Tree)*. 写优化存储引擎原理.
