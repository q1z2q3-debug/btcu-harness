# BTCU Harness × DeepSeek Harness — Integration

**Version: v1.3** (this directory is the official integration payload, archived
at `versions/v1.3_dsh_integration/`).

The **DeepSeek Harness** (dsh, a Cordis/Node agent harness) is fused with the
BTCU cognitive layer. The Python package in this repository is the reference
implementation; this directory carries the harness-side face of the fusion: a
locally authored **agent preset** that mounts an import-free Cordis plugin
(`btcu.mjs`) — a pure JavaScript port of the 1.2.1 core + System 1 pattern
library — and registers six model-facing `btcu_*` tools, together with a
persona teaching the ternary cognitive framework and the dual-system protocol.

## Install

Copy this directory to the dsh agent-presets user root:

```bash
# Windows (this machine)
xcopy integrations\deepseek-harness %USERPROFILE%\.dsh\.agent-presets\btcu\ /E /I

# POSIX
cp -r integrations/deepseek-harness "$HOME/.dsh/.agent-presets/btcu"
```

Then select the **BTCU Cognitive Agent** preset for new sessions (the preset
picker, or `agent-presets.default: btcu` in `$DSH_HOME/settings.yaml`). The
preset composes the full coding agent surface plus the cognitive layer; the
reference Python package can be installed independently with
`pip install -e .` (core deps: pydantic only).

## The six tools

- `btcu_interpret` — map a cognitive state (9-trit vector **or** index) into
  the 19683-state space: index, symbol, polarity, region, per-dimension labels.
- `btcu_ternary` — balanced-ternary vector algebra (add/sub/mul, similarity,
  hamming distance, polarity).
- `btcu_state` — state-space navigation: mirror/opposite, neighbors, distance,
  shortest path, and the path through the void (the creative reset).
- `btcu_third_choice` — conflict analysis and third-choice candidates (void the
  conflicting dimensions, preserve agreement).
- `btcu_decide` — **the dual system**: System 1 cascade (exact hash O(1) → k-NN
  in 9D Euclidean → fuzzy bag-of-words cosine) answers instantly when
  confident; a miss returns `needs_s2: true` and the model deliberates as
  System 2, feeding the outcome back through `feedback` (`state`/`action`/
  `success`) to be learned into System 1 (Bayesian success-rate update,
  mirroring `System1PatternLibrary.learn`). The library persists to
  `$DSH_HOME/btcu/patterns.json` and accumulates across sessions — the
  school → internalize → graduate curve.
- `btcu_patterns` — the graduation meter: pattern count, state coverage of the
  19683 space, reuse/success stats, average confidence.

## Token economics (measured)

The model sees each tool's `name + description + parameters` schema plus the
persona on every request. Measured against dsh's shipped `standard` preset:

| | tool schemas | persona | fixed per-request |
|---|---|---|---|
| `standard` baseline (24 tools) | ~5,766 tok | ~22 tok | ~5,788 tok |
| `btcu` (30 tools, 6 cognitive) | ~6,797 tok | ~249 tok | ~7,046 tok |
| **fusion delta** | **+1,031 tok** | **+227 tok** | **+1,258 tok (~+22%)** |

The dual-system surface costs about +1,260 tokens per request — the *tuition*;
each System 1 hit later saves the model re-deriving the same state/decision in
context (usually far more than 1,260 tokens per saved deliberation). The schema
prefix is KV-cache prefix-stable, so within one session the fixed cost is paid
once per prefix, not per turn.

## Verification

- Python reference suite: `python -m pytest tests` → **336 passed, 1 skipped**
  (includes cognition/dual-system and MCP tests).
- Preset parity (56 assertions): `btcu.mjs` reproduces the 1.2.1 core + System 1
  library reference values exactly.
- Preset mount: the complete preset mounts through dsh's real
  `dsh-agent-presets` roster; the dual system runs end-to-end (learn via
  feedback → System 1 exact hit → graduation stats).

## Version management note

Per the repository policy ("删除旧版本就是删除进化历史"), every version is
preserved: historical rows in `VERSIONS.md`, archives under `versions/`, and
matching git tags. v1.3 adds the DeepSeek Harness integration without removing
anything before it.
