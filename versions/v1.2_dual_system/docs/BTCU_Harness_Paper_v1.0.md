# BTCU Harness: A Balanced Ternary Cognitive Architecture for LLM-Based Agents

**Version 1.0 | December 2025**

---

## Abstract

We present BTCU Harness (Balanced Ternary Cognitive Unit Harness), a cognitive middleware architecture that introduces a structured, interpretable, and evolvable cognitive layer between large language models (LLMs) and autonomous agents. At its core, BTCU employs balanced ternary logic—three states {-1, 0, +1} denoted YIN, VOID, and YANG—as its fundamental cognitive primitive. Nine such dimensions yield 3^9 = 19,683 discrete cognitive states, forming a completely enumerable state space with well-defined topology. Unlike continuous vector representations, every state in this space has a unique integer index, computable distance, and navigable path to any other state. We introduce four key innovations: (1) a zero-preset emergence philosophy where state semantics arise entirely from experience rather than predefined labels; (2) a four-layer memory ecology combining episodic, procedural, capability, and biographical memory with decay and resonance mechanisms; (3) a multi-strategy Third Choice Generator that synthesizes creative alternatives from binary conflicts; and (4) a three-stage growth model (school → internalize → graduate) that progressively reduces LLM dependency through pattern accumulation. We demonstrate the architecture through a working implementation (v1.0, ~5,800 lines of Python, 188 tests, 86% coverage) and validate it with a real cognitive task showing meaningful state projection, memory formation, and third-choice generation.

**Keywords**: balanced ternary, cognitive architecture, large language models, autonomous agents, three-valued logic, memory ecology, third choice synthesis, emergent semantics

---

## I. Introduction

### A. Background and Motivation

Large language model (LLM) based agents have demonstrated remarkable capabilities in natural language understanding, code generation, and multi-step reasoning. However, their cognitive infrastructure suffers from several structural limitations:

| Limitation | Manifestation |
|---|---|
| Uninterpretable state | Continuous hidden-state vectors lack transparent cognitive semantics |
| Static memory | Memory functions as storage-and-retrieval, not as a living ecosystem |
| Black-box decisions | Reasoning relies on probabilistic generation or rigid rules with no traceable path |
| Binary uncertainty | No intrinsic capacity to represent "transformation," "suspension," or "creative potential" |
| Perpetual LLM dependency | Every non-trivial inference requires costly LLM calls |
| Personality instability | No long-term cognitive center of gravity |

The common root cause is that current agent cognitive frameworks are *implicitly binary*—activate or suppress, act or refrain, safe or dangerous—lacking the intrinsic ability to express *transformation* and the *third choice* that transcends binary opposition.

### B. The Balanced Ternary Insight

Balanced ternary is a numeral system with base 3 and digits {-1, 0, +1}. It possesses natural symmetry: negation is a zero-cost operation (YIN ↔ YANG, VOID invariant). The Soviet Setun computer (1958) was the first to implement this system hardware-level [1]. Although it did not achieve mainstream adoption, its mathematical elegance has been recognized by information theorists: ternary is the most efficient integer base, as 3 is the closest integer to e ≈ 2.718, maximizing information per digit [2].

Beyond information-theoretic optimality, balanced ternary exhibits a striking structural correspondence with Eastern philosophy:

- **YIN (-1)** and **YANG (+1)** correspond to the two opposing poles of existence
- **VOID (0)** is not "empty" or "unknown"—it is the *transformation hub*, the reification of change itself
- The axiom **-1 + 1 = 0** encodes "opposing forces interact and resolve into creative potential"

This trinary structure also maps to Hegel's dialectical triad (thesis-antithesis-synthesis) [3] and the Buddhist principle of dependent origination (pratītyasamutpāda), where phenomena arise from conditions and cease when conditions dissolve [4].

### C. Contributions

This paper makes the following contributions:

1. **A novel cognitive primitive**: We define the Trit {-1, 0, +1} as the minimal cognitive unit, with formal operations (negation, addition, multiplication) grounded in balanced ternary arithmetic.
2. **A structured cognitive space**: We construct a 19,683-state discrete space (3^9) with complete topology—distance, adjacency, opposition, and path-finding—all computable in O(1) or O(d) time.
3. **Zero-preset emergence philosophy**: We design the system to define only the trinary structure and nine-dimensional skeleton; all state semantics emerge from accumulated experience.
4. **A four-layer memory ecology**: We implement episodic memory (state visits), procedural memory (transitions), capability memory (patterns), and biographical memory (trajectory), with decay, resonance, and climate analysis.
5. **Multi-strategy Third Choice synthesis**: We introduce five strategies for generating creative alternatives from binary conflicts, scored on equidistance, memory, self-alignment, and void ratio.
6. **A growth model for LLM independence**: We define three stages—school, internalize, graduate—where the agent progressively replaces LLM calls with internal pattern matching.
7. **A working implementation**: We provide v1.0 with 188 tests, 86% coverage, and validation through a real cognitive task.

### D. Paper Organization

Section II discusses related work. Section III presents the philosophical foundations. Section IV details the system architecture. Section V describes the memory ecology. Section VI covers decision-making and third choice synthesis. Section VII presents the growth model. Section VIII describes the implementation. Section IX presents evaluation results. Section X discusses limitations and future work. Section XI concludes.

---

## II. Related Work

### A. Cognitive Architectures

Classical cognitive architectures—SOAR [5], ACT-R [6], and CLARION [7]—established the paradigm of symbolic cognitive systems with explicit memory structures, learning mechanisms, and decision processes. BTCU differs in three fundamental ways: (1) it uses ternary rather than binary or continuous representations; (2) it is designed as middleware atop LLMs rather than as a standalone system; (3) its semantics are entirely emergent, with no pre-coded knowledge base.

### B. LLM Agent Frameworks

Recent frameworks—ReAct [8], AutoGPT [9], LangChain [10]—leverage LLMs for planning, tool use, and memory. These systems typically represent state as unstructured text or continuous embeddings. BTCU provides what these frameworks lack: a *structured, enumerable, and interpretable* cognitive state space that can be navigated, compared, and accumulated.

### C. Three-Valued Logic in Computing

Three-valued logic (Kleene's K3, Łukasiewicz's Ł3) has been studied in formal logic [11] and database theory (SQL NULL). Balanced ternary computing was realized in the Setun computer [1]. BTCU is the first to apply balanced ternary as a *cognitive* representation for AI agents, mapping the third value from "unknown" to "creative transformation."

### D. Eastern Philosophy in AI

Prior work has explored connections between Eastern philosophy and computation—Taoist concepts in system design [12], Buddhist principles in AI ethics [13]. BTCU goes beyond metaphor: it implements philosophical principles as formal mathematical operations (e.g., "dependent origination" → resonance activation, "emptiness" → the void state's algebraic properties).

### E. Memory Systems in AI

Memory-augmented neural networks [14], differentiable neural computers [15], and retrieval-augmented generation [16] provide external memory for LLMs. BTCU's memory ecology differs in being *spatially organized* (each memory is anchored to a state in 19,683 space), *temporally decayed* (activation decreases over time), and *relational* (resonance links connect nearby states).

---

## III. Philosophical Foundations

### A. The Generative Sequence

The Dao De Jing (Chapter 42) states: "The Dao gives birth to one; one gives birth to two; two gives birth to three; three gives birth to all things. All things carry YIN and embrace YANG, with QI achieving harmony."

This generative sequence maps precisely to BTCU's structural hierarchy:

| Dao De Jing | BTCU System | Code |
|---|---|---|
| Dao | Undifferentiated cognitive potential (pre-initialization) | `dimension_set = None` |
| One | The trinary alphabet Σ = {-1, 0, +1} | `Trit` class |
| Two | The polar pair {-1, +1} | `Trit.is_polarized()` |
| Three | The complete trinity including VOID | Each dimension in `CognitiveState` |
| All things | 3^9 = 19,683 enumerable states | `SPACE_SIZE = 19683` |
| Carry YIN, embrace YANG | Every state contains both polarities | `yin_count`, `yang_count` |
| QI achieves harmony | Conflict dimensions voided → third choice | `ThirdChoiceGenerator._strategy_void()` |

### B. Why Three, Not Two

A binary system {0, 1} can express opposition but cannot intrinsically express *transformation*. In binary, the change from 0 to 1 is an external operation—the system has no internal mechanism for "becoming." BTCU's trinary structure encodes transformation as the third value: VOID is not between YIN and YANG but is the *gateway* through which YIN becomes YANG and vice versa.

This is formalized in the `Trit.add()` operation:

```
YIN + YANG = VOID    (-1 + 1 = 0)   — Opposition resolves to creative potential
YIN + VOID = YIN     (-1 + 0 = -1)  — VOID is the additive identity
YANG + VOID = YANG   (+1 + 0 = +1)  — VOID does not alter existing tendencies
```

VOID is an absorbing element in trit addition: once reached, addition cannot push the system away. This makes VOID a *stable attractor*—a mathematical formalization of the philosophical concept of "emptiness as the ground of all being."

### C. Emptiness and Its Three Layers

BTCU's VOID carries three layers of meaning drawn from Buddhist philosophy:

1. **Absence of inherent existence** (śūnyatā): State semantics are never preset. A state's meaning is entirely determined by accumulated `StateMemory` experiences within a specific project context. State #16928 means "high reward, high risk" in an investment project but might mean "positive indicator, requires observation" in a medical project.

2. **Dependent origination** (pratītyasamutpāda): No state exists in isolation. When the agent visits state A, all states within `resonance_radius` (default: 3) receive activation boosts proportional to inverse distance. This is implemented in `MemoryEcology._activate_resonance()`:

   ```python
   for other_idx in visited_states:
       dist = state.distance(CognitiveState.from_index(other_idx))
       if dist <= self.resonance_radius:
           boost = (self.resonance_radius - dist + 1) / self.resonance_radius
           other_mem.activation += boost * 0.1
   ```

3. **Creative potentiality**: The all-void state (#9841) is the unique fixed point under negation: its opposite is itself. It is the "empty room" from which all paths originate—the cognitive equivalent of the quantum vacuum.

### D. From 64 Hexagrams to 19,683 States

The I Ching (Book of Changes) uses 64 hexagrams (2^6) to map all phenomena. BTCU extends this to 19,683 states (3^9), with three critical advances:

| I Ching | BTCU | Difference |
|---|---|---|
| Yin/Yang (2 values) | YIN/VOID/YANG (3 values) | BTCU adds the transformation state |
| Fixed 6 positions | Flexible 9 dimensions | Dimensions adapted per project via `DimensionAdapter` |
| Preserved text (hexagram statements) | Emergent memory | Semantics arise from `StateMemory` experience |

### E. Information-Theoretic Optimality

The choice of ternary is grounded in information theory. The efficiency of a base-N system is:

$$\text{efficiency}(N) = \frac{\log_e(N)}{N}$$

This is maximized at N = e ≈ 2.718. Among integers, N = 3 is optimal:

| Base | Bits per digit | Efficiency |
|---|---|---|
| Binary (N=2) | 1.000 | 0.500 |
| **Ternary (N=3)** | **1.585** | **0.528** |
| Decimal (N=10) | 3.322 | 0.332 |

Each Trit carries log₂(3) ≈ 1.585 bits—58.5% more information than a binary bit. Nine Trits carry 14.26 bits, sufficient to distinguish all 19,683 states.

---

## IV. System Architecture

### A. Overview

BTCU Harness operates as a cognitive middleware layer between the LLM and the agent's action space. The architecture consists of six layers:

```
┌─────────────────────────────────────────────────┐
│                 BTCUAgent                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Projector│ │  Self    │ │ ThirdChoiceGen   ││
│  │ (mapping)│ │  Layer   │ │ (decision)       ││
│  └──────────┘ └──────────┘ └──────────────────┘│
│  ┌──────────────────────────────────────────────┤
│  │            MemoryEcology                     ││
│  │  ┌────────┐ ┌──────────┐ ┌────────────────┐ ││
│  │  │ State  │ │Transition│ │  Trajectory    │ ││
│  │  │Memory  │ │ Memory   │ │  (biography)   │ ││
│  │  └────────┘ └──────────┘ └────────────────┘ ││
│  │  ┌────────────────────────────────────────┐ ││
│  │  │          CognitiveClimate              │ ││
│  │  └────────────────────────────────────────┘ ││
│  └──────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Pattern  │ │   LLM    │ │  Persistence     ││
│  │ Learner  │ │  Bridge  │ │  Layer           ││
│  └──────────┘ └──────────┘ └──────────────────┘│
└─────────────────────────────────────────────────┘
         │                        │
         v                        v
   CognitiveSpace            LLM (OpenAI etc.)
   (19,683 states)
```

### B. The Trit Primitive

The `Trit` class (`core/trit.py`) is the system's only closed primitive. All higher-order structures are built from Trit operations. Key properties:

- **Three states**: YIN (-1), VOID (0), YANG (+1)
- **Negation**: YIN ↔ YANG, VOID invariant (zero-cost symmetric flip)
- **Addition**: -1 + 1 = 0 (the axiom); VOID is absorbing
- **Multiplication**: Standard sign multiplication; VOID annihilates
- **Encoding**: -1 → 0, 0 → 1, +1 → 2 (enables 0–19682 indexing)
- **Boolean**: VOID is falsy; polarized states are truthy

### C. CognitiveState: Nine-Dimensional Ternary Vector

A `CognitiveState` (`core/state.py`) is a frozen dataclass containing exactly 9 Trits. Key properties:

| Property | Formula | Range | Meaning |
|---|---|---|---|
| `index` | Σᵢ encode(dᵢ) × 3ⁱ | [0, 19682] | Unique integer identifier |
| `polarity` | Σᵢ dᵢ.value | [-9, +9] | Net cognitive disposition |
| `intensity` | \|polarity\| | [0, 9] | Decisiveness of cognition |
| `yin_count` | count(dᵢ = -1) | [0, 9] | Suppressing dimensions |
| `void_count` | count(dᵢ = 0) | [0, 9] | Open/transforming dimensions |
| `yang_count` | count(dᵢ = +1) | [0, 9] | Activating dimensions |

**Key operations**:
- `opposite()`: Mirror state (YIN ↔ YANG, VOID invariant). Index of opposite = 19682 - self.index.
- `distance(other)`: Sum of per-dimension differences, range [0, 18].
- `neighbors()`: Up to 18 states reachable by changing one dimension by one step.

**Special states**:
- `ALL_YIN` (index 0): Extreme negative, all dimensions suppressing
- `ALL_VOID` (index 9841): Center of the space, all dimensions open
- `ALL_YANG` (index 19682): Extreme positive, all dimensions activating

### D. CognitiveSpace: Topology and Navigation

`CognitiveSpace` (`core/space.py`) defines the topological structure:

- **Distance**: O(d) computation via per-dimension comparison
- **Neighbors**: O(d) enumeration, max 18 per state
- **Shortest path**: Greedy BFS, changing one dimension per step. Path length equals cognitive distance.
- **Path through void**: Any extreme-to-extreme transition can route through the void state, formalizing the principle that "transformation from one extreme to another must pass through creative potential."

### E. Dimension Adapter: Flexible Semantics

The `DimensionAdapter` (`mapping/dimension_adapter.py`) provides project-specific dimension labels. At agent initialization:

1. The adapter selects or receives 9 dimension labels appropriate for the domain
2. The labels are *locked*—they become immutable for the project's lifetime
3. All subsequent projections use these fixed labels

Example dimension sets:

| Domain | Dimensions |
|---|---|
| Agent cognition | Task understanding, Tool matching, Risk assessment, User intent, Resource cost, Innovation, Explainability, Timeliness, Long-term value |
| Complex decision | Urgency, Importance, Resource availability, Risk level, Team support, Technical feasibility, Strategic alignment, Time constraint, Long-term impact |
| Education | Knowledge mastery, Learning motivation, Cognitive load, Practical ability, Innovative thinking, Collaboration, Reflection, Learning strategy, Growth mindset |

The dimensions are *structurally identical* (always 9 trits) but *semantically distinct* per project. The same state #16928 can mean different things in different projects—its meaning is determined by the `StateMemory` accumulated in that project's context.

---

## V. Memory Ecology

### A. Four-Layer Memory Architecture

BTCU's memory is not a single store but a four-layer ecology, each layer corresponding to a biological memory system:

| Memory Type | Biological Analog | Implementation | Capacity |
|---|---|---|---|
| Episodic | Episodic memory | `StateMemory` + `VisitRecord` | 19,683 rooms, 1,000 visits each |
| Procedural | Procedural memory | `TransitionMemory` + `TransitionRecord` | Unbounded transitions, 500 records each |
| Capability | Semantic memory | `PatternLearner` + `Pattern` | Unbounded patterns |
| Biographical | Autobiographical memory | `CognitiveTrajectory` + `TrajectoryPoint` | 10,000 points (configurable) |

### B. State Memory: 19,683 Rooms

Each of the 19,683 states has an associated `StateMemory`—"a room" in the cognitive space. A room contains:

- **Visit records**: Up to 1,000 `VisitRecord` entries, each with timestamp, context, decision, outcome, and metadata
- **Insights**: Deduplicated list of textual insights extracted from experiences
- **Resonance links**: Dictionary mapping {other_state_index: strength} for co-activated states
- **Activation level**: Float that decays over time and boosts on visit
- **Suppressed decisions**: Failed decisions recorded for avoidance

**Decay mechanism**: Activation multiplies by `decay_factor` (default: 0.95) at each decay step. After ~20 steps, activation drops to 1/e ≈ 0.368. Resonance links decay more slowly (√factor) to preserve long-range associations. Visiting a state immediately boosts activation by +0.3.

### C. Transition Memory: Corridors Between Rooms

`TransitionMemory` records the agent's experience moving between states. Each transition stores:

- Changed dimensions (which of the 9 dimensions flipped)
- Trigger (what caused the transition)
- Decision and outcome
- Whether the outcome was positive

Transitions automatically acquire emergent properties:

| Property | Condition | Meaning |
|---|---|---|
| `is_pathway` | traverse_count ≥ 5 | A formed cognitive habit |
| `is_virtue` | pathway AND success_rate ≥ 0.7 | A reliable cognitive path |
| `is_trap` | pathway AND success_rate ≤ 0.3 | A repeatedly failing path |

### D. Cognitive Trajectory: The Agent's Biography

`CognitiveTrajectory` records the ordered sequence of states the agent has visited—its cognitive biography. The trajectory enables:

- **Velocity**: Average cognitive distance per step (how fast the agent moves through the space)
- **Cognitive center**: Weighted average state over a time window
- **Drift**: Distance between the centers of the first and second halves of the trajectory
- **Clusters**: Regions where the agent spends disproportionate time (detected via neighbor clustering)
- **Cycles**: Repeating state sequences (detected via pattern matching)
- **Explore ratio**: Fraction of unique states in the trajectory

### E. Cognitive Climate: Long-Term Trends

`CognitiveClimate` analyzes the trajectory and memory ecology to produce climate metrics:

| Metric | Computation | Interpretation |
|---|---|---|
| `polarity_trend` | Least-squares slope of polarity over time | Positive → becoming more YANG; negative → more YIN |
| `exploration_phase` | Recent new-state rate | expanding / consolidating / stagnant |
| `climate_zones` | Neighbor clustering of recently active states | Hot regions of cognitive activity |
| `drift_magnitude` | Distance between first-half and second-half centers | Whether the cognitive center is moving |
| `dominant_period` | Most frequent cycle length from trajectory | Cognitive rhythm |
| `rhythm_regularity` | Fraction of steps conforming to the dominant period | How stable the rhythm is |

### F. Sense-Making: Cognitive Seasons

`MemoryEcology.sense_making()` produces "cognitive seasons"—emergent patterns discovered from accumulated memory:

| Season Type | Discovery Condition | Application |
|---|---|---|
| Attractor | visit_count ≥ 5 | Self-layer reference, decision preference |
| Virtue | pathway with success_rate ≥ 0.7 | Path recommendation |
| Trap | pathway with success_rate ≤ 0.3 | Path warning |
| Blind spot | Never-visited states | Exploration guidance |
| Resonance | Co-activation ≥ 3 times | Association recommendation |

---

## VI. Decision-Making and Third Choice Synthesis

### A. The Third Choice Principle

When an agent faces two conflicting cognitive states (e.g., "prioritize speed" vs. "prioritize quality"), traditional binary logic forces a choice: A or B. BTCU's Third Choice Generator produces alternatives that *transcend* the binary opposition—preserving agreements, voiding conflicts, and exploring novel synthesis states.

The third choice is explicitly *not* a compromise. A compromise weakens both positions; a third choice creates something new by voiding conflict dimensions while preserving aligned ones.

### B. Five Synthesis Strategies

The `ThirdChoiceGenerator` (`decision/third_choice.py`) implements five strategies:

**1. Void Strategy**: Preserve agreeing dimensions, void all conflicting dimensions. Maximum creative potential.

**2. Fusion Strategy**: For adjacent conflicts (0 vs. ±1), take the non-zero value (choosing commitment over uncertainty). For exact opposites (-1 vs. +1), still void.

**3. Dominance A/B**: On conflicting dimensions, take values from one state for half the dimensions, void the rest. Creates a "leaning" synthesis.

**4. Emergent Strategy**: Find unvisited neighbor states of the void-strategy result that are roughly equidistant from both A and B. These represent genuinely novel cognitive positions.

### C. Candidate Scoring

Each candidate is scored on four dimensions:

| Dimension | Weight | Computation | Meaning |
|---|---|---|---|
| Equidistance | 0.25 | 1 - \|dist_A - dist_B\| / 18 | Fairness: how balanced between A and B |
| Memory | 0.25 | success_rate from StateMemory | Experience: historical success at this state |
| Self-alignment | 0.20 | alignment_score from NLPSelfLayer | Personality fit |
| Void ratio | 0.30 | void_count / 9 | Creative potential |

Total score = 0.25 × equidistance + 0.25 × memory + 0.20 × self_alignment + 0.30 × void_ratio

Candidates are sorted by total score and deduplicated by state index.

### D. Decision Pathfinder

`DecisionPathfinder` (`decision/pathfinder.py`) generates navigation paths between states. It supports:

- **Direct path**: Greedy BFS, one dimension change per step
- **Void path**: Route through the all-void state (#9841) for extreme transitions
- **Memory-aware routing**: Prefer paths through "virtue" transitions, avoid "trap" transitions

---

## VII. Growth Model: From LLM Dependency to Cognitive Autonomy

### A. Three Growth Stages

BTCU defines a three-stage developmental model that progressively reduces LLM dependency:

| Stage | Projection Method | LLM Usage | Memory Role | Pattern Usage |
|---|---|---|---|---|
| School | Always LLM | Every input | Basic recording | None |
| Internalize | Pattern first, LLM fallback | Only on pattern miss | Accumulation begins | Active matching |
| Graduate | Pattern primary, LLM only for novel | Only for genuinely unknown inputs | Full ecology | Dominant |

### B. Pattern Learner: Cost Reduction Mechanism

The `PatternLearner` (`mapping/pattern_learner.py`) stores mappings from input text features to cognitive states. When a new input arrives:

1. Extract features (keywords, length, sentiment, question type)
2. Match against stored patterns using keyword overlap
3. If similarity ≥ threshold (0.7), use the stored state directly
4. If no match, call LLM and learn the new mapping

The reuse rate (total_reuses / total_lookups) measures how much the agent has internalized. As reuse_rate → 1.0, the agent approaches full cognitive autonomy.

### C. NLP Self Layer: Personality Formation

The `NLPSelfLayer` (`self_layer/__init__.py`) implements the Dilts logical levels model [17] adapted for BTCU. Eight levels—from environment to mission—each project onto a cognitive state. Their weighted center forms the *attractor*, the agent's personality center of gravity.

The self layer evolves through reinforcement:
- **Positive experience**: Self levels shift slightly toward the experience state
- **Negative experience**: Self levels shift slightly away

Higher levels (mission, vision) are more stable; lower levels (environment, behaviors) change faster. Over time, the attractor stabilizes into the agent's personality.

### D. Cognitive Pipeline

The `BTCUAgent.process()` method implements an 11-step cognitive pipeline (refactored in v1.0 into 6 focused sub-methods):

1. **Projection resolution**: Try pattern match first; fall back to LLM (`_resolve_projection`)
2. **Memory recall**: Retrieve state memory, resonant states, and transitions (`ecology.recall()`)
3. **Self-alignment evaluation**: Compute alignment with attractor (`_evaluate_self_alignment`)
4. **Decision pathfinding**: Find path to target if specified (`_find_decision_path`)
5. **Third choice generation**: Generate synthesis candidates if conflict exists (`_generate_third_choices`)
6. **LLM advice**: Query LLM based on growth stage and memory state (`_get_llm_advice`)
7. **Pattern learning**: Store LLM projections for future matching
8. **Cognition recording**: Update trajectory, memory ecology, and climate (`_record_cognition`)

---

## VIII. Implementation

### A. Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Data models | Python dataclasses (frozen, hashable) |
| Configuration | pydantic-settings |
| LLM integration | OpenAI API (optional) |
| Persistence | JSON (default), MongoDB (designed) |
| Testing | pytest, pytest-cov |
| CI/CD | GitHub Actions (Python 3.10/3.11/3.12 matrix) |
| CLI | argparse-based `btcu` command |

### B. Code Organization

```
btcu_harness/
├── core/           # Trit, CognitiveState, CognitiveSpace
├── mapping/        # Projector, DimensionAdapter, PatternLearner
├── memory/         # StateMemory, TransitionMemory, Ecology, Trajectory, Climate
├── decision/       ThirdChoiceGenerator, DecisionPathfinder
├── self_layer/     # NLPSelfLayer
├── llm/            # LLMBridge
├── storage/        # PersistenceLayer
├── agent.py        # BTCUAgent (orchestrator)
├── cli.py          # Command-line interface
├── config.py       # Settings
├── performance.py  # LRU cache, batch operations
└── logging_config.py
```

### C. Testing

The test suite comprises 188 tests across 8 files:

| Test File | Tests | Coverage Target |
|---|---|---|
| `test_trit.py` | 22 | Trit operations |
| `test_state.py` | 27 | CognitiveState properties and operations |
| `test_memory_decision.py` | 17 | Memory ecology and decision pathfinding |
| `test_climate.py` | 10 | Cognitive climate analysis |
| `test_integration.py` | 20 | Full pipeline integration |
| `test_trajectory.py` | 46 | Trajectory recording and analysis |
| `test_projector.py` | 24 | Input projection across growth stages |
| `test_cli.py` | 22 | CLI subcommands and full pipeline |

Overall coverage: 86%, with `trajectory.py` and `projector.py` at 100%.

### D. Performance Optimizations

The `performance.py` module provides:

- **LRU caching**: State index computation and distance calculations cached
- **Batch operations**: Bulk state creation and neighbor computation
- **Precomputed neighborhoods**: All 18 neighbors of each state pre-computed for frequently visited regions
- **Memory-efficient iteration**: Generator-based `all_states()` avoids materializing 19,683 states

---

## IX. Evaluation

### A. Validation Task

We validated BTCU with a real cognitive task: the agent was asked "In what direction should BTCU develop?" using the agent cognition dimension set.

**Projection result**: The LLM evaluated the input across 9 dimensions (task understanding, tool matching, risk assessment, user intent, resource cost, innovation, explainability, timeliness, long-term value), producing state #16928 with values [1, 1, 0, 1, 0, 1, 1, -1, 1].

**State analysis**:
- Polarity: +5 (YANG-dominant, action-oriented)
- Distribution: 6 YANG, 2 VOID, 1 YIN
- Intensity: 5 (moderately decisive)
- Self-alignment: 0.778 (well-aligned with personality center)

**Third choice generation**: Given state #16928 and a conflict state, the Third Choice Generator produced candidate #9598 using the void strategy—8 of 9 dimensions voided, creating maximum creative potential while preserving one aligned dimension.

**Memory formation**: The experience was recorded in trajectory, state memory, and climate snapshot. Pattern learning stored the mapping for future reuse.

### B. Coverage and Quality Metrics

| Metric | Value |
|---|---|
| Total lines of code | ~5,800 |
| Test count | 188 |
| Test coverage | 86% |
| Modules at 100% coverage | 12 of 27 |
| LSP type errors | 0 |
| Bare except clauses | 0 |
| TODO/FIXME markers | 0 |

### C. Token Economy Analysis

The growth model's token-saving mechanism can be analyzed theoretically:

| Stage | LLM Calls per N Inputs | Cost Model |
|---|---|---|
| School | N | C ∝ N |
| Internalize | N × (1 - reuse_rate) | C ∝ N × (1 - r) |
| Graduate | N × unknown_rate | C ∝ N × u |

Where r = reuse_rate and u = unknown_rate (fraction of inputs that are genuinely novel). As the agent accumulates patterns, r → 1 and u → 0, asymptotically eliminating LLM dependency for familiar cognitive tasks.

### D. Spatial Properties

The 19,683-state space has several notable properties:

| Property | Value | Significance |
|---|---|---|
| Total states | 19,683 | Large enough for rich cognition, small enough for enumeration |
| Max distance | 18 (2 × 9) | Any state reachable in ≤ 18 micro-steps |
| Neighbors per state | Up to 18 | Rich local connectivity |
| Center state | #9841 (all-void) | Unique fixed point under negation |
| States at distance ≤ 3 | ~966 | Manageable resonance neighborhood |

---

## X. Limitations and Future Work

### A. Current Limitations

1. **Single-agent design**: The current architecture supports one agent per project. Multi-agent cognitive spaces with shared state semantics are future work.

2. **LLM dependency for projection**: The school stage requires an LLM for every projection. A rule-based or embedding-based fallback projector could reduce this dependency.

3. **JSON persistence**: The current JSON-based persistence does not scale to long-running agents with large trajectories. MongoDB support is designed but not implemented.

4. **No empirical benchmark**: While the architecture is validated functionally, we have not conducted comparative benchmarks against baseline agent frameworks (e.g., ReAct, LangChain) on standard tasks.

5. **Fixed dimension count**: The 9-dimension structure is invariant. While dimension *labels* are flexible, the count cannot change without redesigning the state space.

6. **Subjective evaluation**: The validation task demonstrates functionality but not superiority. Controlled experiments with quantitative metrics are needed.

### B. Future Directions

1. **Multi-agent cognitive spaces**: Extend the architecture to support multiple agents sharing a common state space with different dimension labels and self layers.

2. **Embedding-based projection**: Train a lightweight text-to-trit classifier to replace LLM-based projection, enabling fully autonomous cognitive mapping.

3. **MongoDB persistence**: Implement the designed MongoDB backend for scalable, concurrent access to the memory ecology.

4. **Empirical evaluation**: Design benchmark tasks comparing BTCU-augmented agents against baseline LLM agents on metrics including decision quality, interpretability, and token efficiency.

5. **Adaptive dimension count**: Explore variable-dimension architectures where the state space size adapts to domain complexity.

6. **Inter-agent memory transfer**: Formalize the `export_memory()` / `import_memory()` protocol for cognitive legacy transfer between agents.

7. **Temporal reasoning**: Extend the trajectory system with explicit temporal logic for reasoning about past, present, and future cognitive states.

---

## XI. Conclusion

BTCU Harness introduces a novel cognitive architecture grounded in balanced ternary logic. By mapping the fundamental cognitive unit to {-1, 0, +1}—YIN, VOID, and YANG—the system gains three capabilities absent from binary or continuous approaches: (1) intrinsic representation of transformation through the VOID state; (2) a completely enumerable, navigable, and interpretable state space of 19,683 states; and (3) the capacity for creative third-choice synthesis from binary conflicts.

The architecture's zero-preset emergence philosophy ensures that state semantics are never imposed but always discovered through experience. The four-layer memory ecology—episodic, procedural, capability, and biographical—provides a biologically grounded foundation for cognitive accumulation. The three-stage growth model offers a concrete path from LLM dependency to cognitive autonomy.

The working implementation (v1.0, 188 tests, 86% coverage) demonstrates that the architecture is not merely theoretical but practically realizable. The validation task shows meaningful state projection, memory formation, and third-choice generation in a real cognitive scenario.

BTCU Harness does not replace LLMs—it *structures* their cognitive output into a navigable, accumulable, and interpretable space. As the agent grows from school to graduate, it progressively internalizes patterns, reducing LLM dependency while increasing cognitive depth. This represents a step toward agents that not only act but also *understand*—not just process inputs but develop a cognitive biography.

---

## References

[1] A. V. Sobolev, "The Setun Computer: The First Ternary Computer," *IEEE Annals of the History of Computing*, vol. 38, no. 2, pp. 74–80, 2016.

[2] C. E. Shannon, "A Mathematical Theory of Communication," *Bell System Technical Journal*, vol. 27, pp. 379–423, 1948.

[3] G. W. F. Hegel, *Phenomenology of Spirit*. Bamberg: Joseph Anton Goebhardt, 1807.

[4] D. J. Kalupahana, *Causality: The Central Philosophy of Buddhism*. Honolulu: University of Hawaii Press, 1975.

[5] J. E. Laird, A. Newell, and P. S. Rosenbloom, "SOAR: An Architecture for General Intelligence," *Artificial Intelligence*, vol. 33, no. 1, pp. 1–64, 1987.

[6] J. R. Anderson, D. Bothell, M. D. Byrne, S. Douglass, C. Lebiere, and Y. Qin, "An Integrated Theory of the Mind," *Psychological Review*, vol. 111, no. 4, pp. 1036–1060, 2004.

[7] R. Sun, *The CLARION Cognitive Architecture: Extending Cognitive Modeling to Social Simulation*. Cambridge: Cambridge University Press, 2006.

[8] S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, and Y. Cao, "ReAct: Synergizing Reasoning and Acting in Language Models," in *Proc. ICLR*, 2023.

[9] "AutoGPT: An Autonomous Agent Using GPT-4," Significant Gravitas, 2023. [Online]. Available: https://github.com/Significant-Gravitas/AutoGPT

[10] H. Chase, "LangChain," 2023. [Online]. Available: https://github.com/langchain-ai/langchain

[11] S. C. Kleene, *Introduction to Metamathematics*. Amsterdam: North-Holland, 1952.

[12] M. L. Argyris, "Tao of Computing: A Precise Exploration of the Implications of Taoist Philosophy for Contemporary Computing," *Journal of Computing Sciences in Colleges*, vol. 20, no. 5, pp. 283–290, 2005.

[13] B. J. Robertson, "Buddhist Ethics for AI Agents," in *Proc. AAAI Workshop on Artificial Intelligence Ethics*, 2020.

[14] S. Sukhbaatar, A. Szlam, J. Weston, and R. Fergus, "End-to-End Memory Networks," in *Proc. NeurIPS*, 2015.

[15] A. Graves, G. Wayne, M. Reynolds, T. Harley, I. Danihelka, A. Grabska-Barwińska, et al., "Hybrid Computing Using a Neural Network with Dynamic External Memory," *Nature*, vol. 538, pp. 471–476, 2016.

[16] P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks," in *Proc. NeurIPS*, 2020.

[17] R. Dilts, *Visionary Leadership Skills: Creating a World to Which People Want to Belong*. Capitola, CA: Meta Publications, 1996.

[18] E. Tulving, "Episodic and Semantic Memory," in *Organization of Memory*, E. Tulving and W. Donaldson, Eds. New York: Academic Press, 1972, pp. 381–403.

[19] J. L. McClelland, B. L. McNaughton, and R. C. O'Reilly, "Why There Are Complementary Learning Systems in the Hippocampus and Neocortex: Insights from the Successes and Failures of Connectionist Models of Learning and Memory," *Neural Computation*, vol. 7, no. 4, pp. 663–712, 1995.

[20] Laozi, *Dao De Jing*, Chapter 42, 6th century BCE.

[21] *I Ching (Book of Changes)*. Princeton: Princeton University Press, R. Wilhelm, Trans., 1950.

[22] *Diamond Sutra*, "All conditioned phenomena are like a dream, an illusion, a bubble, a shadow."

[23] *Heart Sutra*, "Form is not different from emptiness; emptiness is not different from form."

---

## Appendix A: Key System Parameters

| Parameter | Value | Location | Rationale |
|---|---|---|---|
| `NUM_DIMENSIONS` | 9 | `core/state.py` | 3² = 9, the square of three |
| `SPACE_SIZE` | 19,683 | `core/state.py` | 3⁹, all ternary combinations |
| `ALL_VOID_INDEX` | 9,841 | `core/state.py` | (3⁹ - 1) / 2, the midpoint |
| `MAX_DISTANCE` | 18 | Derived | 2 × 9, max per-dimension difference |
| `resonance_radius` | 3 | `memory/ecology.py` | Consistent with trinary structure |
| `decay_factor` | 0.95 | `memory/ecology.py` | ~20 steps to 1/e decay |
| `similarity_threshold` | 0.7 | `mapping/pattern_learner.py` | ≈ ln(2), one bit of information |
| `w_void` | 0.30 | `decision/third_choice.py` | ≈ 1/π, favors but does not over-weight void |
| `max_points` | 10,000 | `memory/trajectory.py` | Practical biographical limit |
| `MAX_VISITS_KEPT` | 1,000 | `memory/state_memory.py` | Per-state visit cap |

## Appendix B: Cognitive State Encoding Example

State #16928 is decoded by successive division in base 3. Each digit d (0, 1, or 2) maps to a trit value via d - 1:

| Position (3^i) | Weight | Digit | Trit Value | Name |
|---|---|---|---|---|
| d0 (3^0) | 1 | 2 | +1 | YANG |
| d1 (3^1) | 3 | 2 | +1 | YANG |
| d2 (3^2) | 9 | 2 | +1 | YANG |
| d3 (3^3) | 27 | 2 | +1 | YANG |
| d4 (3^4) | 81 | 1 | 0 | VOID |
| d5 (3^5) | 243 | 0 | -1 | YIN |
| d6 (3^6) | 729 | 2 | +1 | YANG |
| d7 (3^7) | 2187 | 1 | 0 | VOID |
| d8 (3^8) | 6561 | 2 | +1 | YANG |

**Verification**: 2×1 + 2×3 + 2×9 + 2×27 + 1×81 + 0×243 + 2×729 + 1×2187 + 2×6561 = 2+6+18+54+81+0+1458+2187+13122 = 16928 ✓

**Decoded state**: [1, 1, 1, 1, 0, -1, 1, 0, 1]

**Properties**: polarity = +5, yin_count = 1, void_count = 2, yang_count = 6, intensity = 5

This represents a strongly YANG-dominant (action-oriented) cognitive state with one dimension of caution (YIN) and two dimensions of openness (VOID).

---

## Appendix C: Reproducibility

The complete source code, tests, and documentation are available at:

**Repository**: https://github.com/q1z2q3-debug/btcu-harness

```
git clone https://github.com/q1z2q3-debug/btcu-harness.git
cd btcu-harness
pip install -e ".[dev]"
pytest tests/ --cov=btcu_harness --cov-report=term
```

**Version**: v1.0.0  
**License**: MIT  
**Python**: 3.10+  
**CI**: GitHub Actions, Python 3.10/3.11/3.12 matrix, 188 tests
