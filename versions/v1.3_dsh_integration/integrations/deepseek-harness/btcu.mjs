// BTCU cognitive layer v1.2.1 — pure-JS port of the reference Python
// implementation (vendored at python/btcu-harness in the DeepSeek Harness
// repository, upstream https://github.com/q1z2q3-debug/btcu-harness, MIT).
//
// Import-free of bare specifiers on purpose (the preset is loaded through
// Node's ESM resolver from a directory with no node_modules of its own);
// only node: builtins are used. Registers the btcu_* tools into the host
// `tools` registry (a hard dependency, hence `inject`).
//
// Surface (token-lean, dual-system):
//   btcu_interpret / btcu_ternary / btcu_state / btcu_third_choice — the
//     deterministic core (System 0: always fast, always correct).
//   btcu_decide — Kahneman-style System 1 cascade (exact hash → k-NN in 9D →
//     fuzzy text) with S2→S1 feedback learning; the LLM itself is System 2.
//   btcu_patterns — the graduation meter: coverage/reuse/confidence stats.
//
// The System 1 pattern library is persisted under $DSH_HOME/btcu/patterns.json
// so knowledge survives restarts and accumulates across sessions — the
// "school → internalize → graduate" curve made operational.
//
// Core identity: -1 + 1 = 0. Opposing cognitive states entering the EMPTY
// state is the creative gateway to third-choice generation, not cancellation.

import { createHash } from 'node:crypto'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'

export const name = 'btcu'
export const inject = ['tools']

// ── balanced ternary primitives ────────────────────────────────────────────

const T = -1 // YIN   — negation, retreat, contraction
const Z = 0 //  EMPTY — transformation, creativity, waiting
const O = 1 //  YANG  — affirmation, advance, expansion

const DIM = 9 // 3^9 = 19683 states
const SPACE_SIZE = 19683
const MIN_INDEX = 0
const MAX_INDEX = 19682
const CENTER = 9841 // the all-EMPTY center

const VALID = new Set([T, Z, O])
const SYMBOLS = { [-1]: 'T', [0]: '0', [1]: '1' }
const TRIT_NAMES = { [-1]: 'YIN', [0]: 'EMPTY', [1]: 'YANG' }
const DEFAULT_LABELS = ['time', 'space', 'causality', 'value', 'relation', 'action', 'subject', 'intent', 'cognition']

// ── core helpers (mirroring btcu_harness.core) ─────────────────────────────

function assertTritArray(value, name = 'vector') {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${name} must be a non-empty array of trits (-1, 0, or 1)`)
  }
  for (let i = 0; i < value.length; i++) {
    const v = value[i]
    if (typeof v !== 'number' || !Number.isInteger(v) || !VALID.has(v)) {
      throw new Error(`invalid trit at ${name}[${i}]: ${v} (must be -1, 0, or 1)`)
    }
  }
}

function assertStateVector(value) {
  assertTritArray(value, 'vector')
  if (value.length !== DIM) {
    throw new Error(`a cognitive state requires exactly ${DIM} trits, got ${value.length}`)
  }
}

function assertIndex(value, name = 'index') {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < MIN_INDEX || value > MAX_INDEX) {
    throw new Error(`${name} ${value} out of range [0, ${MAX_INDEX}]`)
  }
}

/** Encode a nine-trit vector (least significant first) into [0, 19682]. */
function encode(vector) {
  assertStateVector(vector)
  let index = 0
  let multiplier = 1
  for (const d of vector) {
    index += (d + 1) * multiplier // -1 -> 0, 0 -> 1, +1 -> 2
    multiplier *= 3
  }
  return index
}

/** Decode an index into a nine-trit vector (least significant first). */
function decode(index) {
  assertIndex(index)
  const vector = []
  let remaining = index
  for (let k = 0; k < DIM; k++) {
    const t = remaining % 3
    remaining = Math.floor(remaining / 3)
    vector.push(t - 1) // 0 -> -1, 1 -> 0, 2 -> +1
  }
  return vector
}

/** Render a vector as a compact symbol string, most significant first. */
function symbolString(vector) {
  return vector.slice().reverse().map(v => SYMBOLS[v]).join('')
}

function counts(vector) {
  return {
    yin_count: vector.filter(v => v === T).length,
    void_count: vector.filter(v => v === Z).length,
    yang_count: vector.filter(v => v === O).length,
  }
}

/** Full interpretation of one state index, mirroring Space19683.interpret(). */
function interpret(index, labels = DEFAULT_LABELS) {
  assertIndex(index)
  const vector = decode(index)
  const { yin_count, void_count, yang_count } = counts(vector)
  const polarity = yin_count * T + yang_count * O
  const region = index === MIN_INDEX
    ? 'all-yin'
    : index === MAX_INDEX
      ? 'all-yang'
      : index === CENTER
        ? 'all-empty'
        : polarity < 0
          ? 'yin-leaning'
          : polarity > 0
            ? 'yang-leaning'
            : 'balanced'
  return {
    index,
    vector,
    symbol: symbolString(vector),
    polarity,
    intensity: Math.abs(polarity),
    ...counts(vector),
    is_void_dominant: void_count >= Math.max(yin_count, yang_count),
    balanced_value: index - CENTER,
    region,
    dimensions: vector.map((v, i) => ({
      label: labels[i] ?? `dim_${i}`,
      trit: v,
      name: TRIT_NAMES[v],
    })),
  }
}

// ── balanced ternary algebra (mirroring btcu_harness.core.ternary) ─────────

function negateVector(a) {
  assertTritArray(a)
  return a.map(v => -v)
}

function addVectors(a, b) {
  assertTritArray(a, 'a')
  assertTritArray(b, 'b')
  const maxLen = Math.max(a.length, b.length)
  const result = []
  let carry = Z
  for (let i = 0; i < maxLen; i++) {
    const av = i < a.length ? a[i] : Z
    const bv = i < b.length ? b[i] : Z
    const total = av + bv + carry
    if (total >= 2) {
      result.push(total - 3)
      carry = O
    } else if (total <= -2) {
      result.push(total + 3)
      carry = T
    } else {
      result.push(total)
      carry = Z
    }
  }
  if (carry !== Z) result.push(carry)
  return result
}

function mulVectors(a, b) {
  assertTritArray(a, 'a')
  assertTritArray(b, 'b')
  const n = Math.min(a.length, b.length)
  return a.slice(0, n).map((v, i) => v * b[i])
}

// ── state-space navigation (mirroring CognitiveState / Space19683) ─────────

/** Up to 18 neighbors: one dimension changed by one step (-1<->0, 0<->+1). */
function neighbors(index) {
  assertIndex(index)
  const vector = decode(index)
  const out = []
  for (let i = 0; i < DIM; i++) {
    if (vector[i] > T) {
      const next = vector.slice()
      next[i] = vector[i] - 1
      out.push(encode(next))
    }
    if (vector[i] < O) {
      const next = vector.slice()
      next[i] = vector[i] + 1
      out.push(encode(next))
    }
  }
  return out
}

/** Cognitive distance: sum of per-dimension absolute differences (0..18). */
function distance(a, b) {
  assertIndex(a, 'a')
  assertIndex(b, 'b')
  const va = decode(a)
  const vb = decode(b)
  return va.reduce((sum, v, i) => sum + Math.abs(v - vb[i]), 0)
}

/** Greedy per-dimension path between two states. */
function pathBetween(a, b) {
  assertIndex(a, 'a')
  assertIndex(b, 'b')
  const target = decode(b)
  const steps = [a]
  let current = decode(a)
  for (let i = 0; i < DIM; i++) {
    while (current[i] !== target[i]) {
      const next = current.slice()
      next[i] += current[i] < target[i] ? 1 : -1
      current = next
      steps.push(encode(current))
    }
  }
  return steps
}

// ── third choice (mirroring btcu_harness.decision.third_choice) ────────────

function analyzeConflict(a, b) {
  const va = decode(a)
  const vb = decode(b)
  const conflictDims = []
  for (let i = 0; i < DIM; i++) {
    if ((va[i] === O && vb[i] === T) || (va[i] === T && vb[i] === O)) conflictDims.push(i)
  }
  return {
    has_conflict: conflictDims.length > 0,
    is_extreme_conflict: conflictDims.length === DIM,
    conflict_dims: conflictDims,
  }
}

function equidistanceScore(c, a, b) {
  const da = distance(c, a)
  const db = distance(c, b)
  const total = da + db
  if (total === 0) return 1.0
  return 1 - Math.abs(da - db) / total
}

function round4(x) {
  return Math.round(x * 10000) / 10000
}

function thirdChoiceCandidates(a, b, labels) {
  assertIndex(a, 'a')
  assertIndex(b, 'b')
  const conflict = analyzeConflict(a, b)
  const allDims = Array.from({ length: DIM }, (_, i) => i)
  const preservedDims = allDims.filter(i => !conflict.conflict_dims.includes(i))
  const candidates = []

  // void strategy: conflicting dimensions become EMPTY, agreement preserved
  const voidValues = decode(a)
  for (const dim of conflict.conflict_dims) voidValues[dim] = Z
  const voidState = encode(voidValues)
  candidates.push(makeCandidate('void', voidState, a, b, conflict.conflict_dims, preservedDims, labels))

  // dominance strategies: keep one side entirely
  candidates.push(makeCandidate('dominance_a', a, a, b, [], allDims, labels))
  candidates.push(makeCandidate('dominance_b', b, a, b, [], allDims, labels))

  return { conflict, candidates }
}

function makeCandidate(strategy, state, a, b, voidedDims, preservedDims, labels) {
  const equidistance = equidistanceScore(state, a, b)
  const voidRatio = voidedDims.length / DIM
  const total = 0.5 * equidistance + 0.5 * voidRatio + 0.01
  const info = interpret(state, labels)
  return {
    strategy,
    state,
    symbol: info.symbol,
    region: info.region,
    polarity: info.polarity,
    voided_dims: voidedDims,
    preserved_dims: preservedDims,
    total_score: round4(total),
    equidistance_score: round4(equidistance),
    void_ratio: round4(voidRatio),
  }
}

// ── System 1 pattern library (mirroring btcu_harness.cognition.system1) ────

const EXACT_CONFIDENCE = 0.6 // System1PatternLibrary.EXACT_CONFIDENCE_THRESHOLD
const KNN_CONFIDENCE_THRESHOLD = 0.5 // System1PatternLibrary.KNN_CONFIDENCE_THRESHOLD
const FUZZY_THRESHOLD = 0.5 // System1PatternLibrary.FUZZY_CONFIDENCE_THRESHOLD
const KNN_DISTANCE_THRESHOLD = 4 // cascade heuristic: trust a neighbor within this 9D Euclidean distance

// bag-of-words stopwords mirrored from System1PatternLibrary._extract_text_features
const PY_STOPWORDS = new Set([
  'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all',
  'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day',
  'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new',
  'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did',
  'she', 'use', 'man', 'men', 'run', 'sun',
])

function inputHash(text) {
  return createHash('sha256').update(String(text), 'utf8').digest('hex')
}

function textFeatures(text) {
  // mirrors System1PatternLibrary._extract_text_features: pure bag-of-words,
  // words longer than 2 chars, frequency normalized by total words.
  const words = String(text).toLowerCase()
    .split(/\s+/)
    .map(w => w.replace(/[.,!?;:"'()[\]]/g, ''))
    .filter(w => w.length > 2)
  const features = {}
  const freq = {}
  for (const w of words) {
    if (!PY_STOPWORDS.has(w)) freq[w] = (freq[w] ?? 0) + 1
  }
  const total = words.length || 1
  for (const [word, count] of Object.entries(freq)) {
    features[word] = count / total
  }
  return features
}

function cosine(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  let dot = 0
  let na = 0
  let nb = 0
  for (const k of keys) {
    const va = a[k] ?? 0
    const vb = b[k] ?? 0
    dot += va * vb
    na += va * va
    nb += vb * vb
  }
  if (na === 0 || nb === 0) return 0
  return dot / (Math.sqrt(na) * Math.sqrt(nb))
}

function euclidean9d(a, b) {
  const va = decode(a)
  const vb = decode(b)
  let sum = 0
  for (let i = 0; i < DIM; i++) sum += (va[i] - vb[i]) ** 2
  return Math.sqrt(sum)
}

/**
 * System1PatternLibrary — persisted fast-path memory.
 * Mirrors System1PatternLibrary: learn (reinforce on exact), match_exact,
 * match_knn (9D Euclidean), match_fuzzy (bag-of-words cosine), coverage.
 */
class System1PatternLibrary {
  constructor() {
    this.patterns = [] // {hash, query, state_index, action, confidence, use_count, success_count, last_seen}
    this.byHash = new Map() // hash -> pattern[]
  }

  static fromFile(path) {
    const lib = new System1PatternLibrary()
    try {
      if (existsSync(path)) {
        const data = JSON.parse(readFileSync(path, 'utf8'))
        lib.patterns = Array.isArray(data.patterns) ? data.patterns : []
        lib._rebuild()
      }
    } catch {
      lib.patterns = []
      lib._rebuild()
    }
    return lib
  }

  save(path) {
    try {
      mkdirSync(join(path, '..'), { recursive: true })
      writeFileSync(path, JSON.stringify({ version: 1, patterns: this.patterns }, null, 2), 'utf8')
    } catch {
      // persistence is best-effort; the in-memory library still works
    }
  }

  _rebuild() {
    this.byHash = new Map()
    for (const p of this.patterns) {
      const list = this.byHash.get(p.hash) ?? []
      list.push(p)
      this.byHash.set(p.hash, list)
    }
  }

  learn(query, stateIndex, action, success = true) {
    assertIndex(stateIndex, 'state')
    const hash = inputHash(query)
    const existing = (this.byHash.get(hash) ?? []).find(p => p.state_index === stateIndex)
    if (existing) {
      existing.use_count += 1
      // Bayesian-like success-rate update, mirroring System1PatternLibrary.learn
      existing.success_rate = success
        ? (existing.success_rate * existing.use_count + 1) / (existing.use_count + 1)
        : (existing.success_rate * existing.use_count) / (existing.use_count + 1)
      existing.last_seen = Date.now()
      existing.confidence = round4(existing.success_rate) // recency ~ 1 right after reinforcement
      return existing
    }
    const pattern = {
      hash,
      query: String(query).slice(0, 200),
      state_index: stateIndex,
      action: String(action ?? '').slice(0, 100),
      success_rate: success ? 1 : 0,
      confidence: success ? 1.0 : 0.0, // mirroring CognitivePattern(confidence=1.0 if success else 0.0)
      use_count: 1,
      success_count: success ? 1 : 0,
      last_seen: Date.now(),
    }
    this.patterns.push(pattern)
    const list = this.byHash.get(hash) ?? []
    list.push(pattern)
    this.byHash.set(hash, list)
    return pattern
  }

  matchExact(query) {
    const list = this.byHash.get(inputHash(query))
    if (!list?.length) return undefined
    const best = [...list].sort((a, b) => b.confidence - a.confidence)[0]
    return best.confidence >= EXACT_CONFIDENCE ? best : undefined
  }

  matchKnn(stateIndex, k = 3) {
    const scored = this.patterns
      .map(p => ({ pattern: p, distance: euclidean9d(p.state_index, stateIndex) }))
      .sort((a, b) => a.distance - b.distance || b.pattern.confidence - a.pattern.confidence)
      .slice(0, k)
    return scored.filter(k => k.pattern.confidence >= KNN_CONFIDENCE_THRESHOLD)
  }

  matchFuzzy(query, threshold = FUZZY_THRESHOLD) {
    const features = textFeatures(query)
    let best
    let bestSim = 0
    for (const p of this.patterns) {
      const sim = cosine(features, p.features ?? textFeatures(p.query))
      if (sim > bestSim) {
        bestSim = sim
        best = p
      }
    }
    return bestSim >= threshold ? { pattern: best, similarity: round4(bestSim) } : undefined
  }

  stats() {
    const covered = new Set(this.patterns.map(p => p.state_index))
    const totalUses = this.patterns.reduce((s, p) => s + p.use_count, 0)
    const totalReuses = this.patterns.reduce((s, p) => s + Math.max(0, p.use_count - 1), 0) // creation is not a reuse
    const successes = this.patterns.reduce((s, p) => s + p.success_count, 0)
    const avgConfidence = this.patterns.length
      ? round4(this.patterns.reduce((s, p) => s + p.confidence, 0) / this.patterns.length)
      : 0
    return {
      pattern_count: this.patterns.length,
      covered_states: covered.size,
      coverage: round4(covered.size / SPACE_SIZE),
      total_reuses: totalReuses,
      success_count: successes,
      success_rate: totalUses ? round4(successes / totalUses) : 0,
      avg_confidence: avgConfidence,
      top_states: [...covered].slice(0, 8),
    }
  }
}

// ── tool registration ──────────────────────────────────────────────────────

// Pure core re-exported for verification against the Python reference
// implementation; the Cordis loader only reads name/inject/apply.
export {
  T, Z, O, DIM, SPACE_SIZE, MIN_INDEX, MAX_INDEX, CENTER,
  encode, decode, interpret, symbolString,
  negateVector, addVectors, mulVectors, neighbors, distance, pathBetween,
  analyzeConflict, thirdChoiceCandidates,
  System1PatternLibrary, inputHash, textFeatures, cosine, euclidean9d,
}

const text = (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }]

const integer = { type: 'integer' }
const tritArray = {
  type: 'array',
  description: 'Trits: -1 (YIN), 0 (EMPTY), +1 (YANG).',
  items: { type: 'integer', minimum: -1, maximum: 1 },
}
const indexField = { ...integer, minimum: 0, maximum: 19682, description: 'State index in [0, 19682]; 9841 = all-EMPTY center.' }
const vec9 = { ...tritArray, minItems: 9, maxItems: 9, description: 'Nine trits, least significant first.' }

// interpretation shape shared by all tools that return full state info
const interpretationSchema = {
  type: 'object',
  additionalProperties: false,
  properties: {
    index: integer,
    vector: { type: 'array', items: integer },
    symbol: { type: 'string' },
    polarity: integer,
    intensity: integer,
    yin_count: integer,
    void_count: integer,
    yang_count: integer,
    is_void_dominant: { type: 'boolean' },
    balanced_value: integer,
    region: { type: 'string' },
    dimensions: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          label: { type: 'string' },
          trit: integer,
          name: { type: 'string' },
        },
        required: ['label', 'trit', 'name'],
      },
    },
  },
  required: ['index', 'vector', 'symbol', 'polarity', 'intensity', 'yin_count', 'void_count', 'yang_count', 'is_void_dominant', 'balanced_value', 'region', 'dimensions'],
}

const patternSchema = {
  type: 'object',
  additionalProperties: false,
  properties: {
    hash: { type: 'string' },
    query: { type: 'string' },
    state_index: integer,
    action: { type: 'string' },
    confidence: { type: 'number' },
    use_count: integer,
    success_count: integer,
    interpretation: interpretationSchema,
  },
  required: ['hash', 'query', 'state_index', 'action', 'confidence', 'use_count', 'success_count', 'interpretation'],
}

export function apply(ctx, config) {
  const labels = Array.isArray(config?.dimensionLabels) && config.dimensionLabels.length === DIM
    ? config.dimensionLabels.map(String)
    : DEFAULT_LABELS

  const dshHome = typeof process !== 'undefined' && process.env?.DSH_HOME
    ? process.env.DSH_HOME
    : join(homedir(), '.dsh')
  const patternsPath = join(dshHome, 'btcu', 'patterns.json')
  const s1 = System1PatternLibrary.fromFile(patternsPath)

  const withInterpretation = (p) => ({
    hash: p.hash,
    query: p.query,
    state_index: p.state_index,
    action: p.action,
    confidence: round4(p.confidence),
    use_count: p.use_count,
    success_count: p.success_count,
    interpretation: interpret(p.state_index, labels),
  })

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_interpret',
    description: 'Map a cognitive state (9-trit vector or index) into the 19683-state space: index, symbol, polarity, region, and per-dimension labels. Use instead of hand-computing.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      description: 'Exactly one of index or vector.',
      properties: {
        index: indexField,
        vector: vec9,
      },
    },
    output: { schema: interpretationSchema, render: text },
    async execute(args) {
      const hasIndex = args.index !== undefined
      const hasVector = args.vector !== undefined
      if (hasIndex === hasVector) {
        throw new Error('provide exactly one of index or vector')
      }
      return interpret(hasVector ? encode(args.vector) : args.index, labels)
    },
  }))

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_ternary',
    description: 'Balanced-ternary algebra on trit vectors: neg, add, sub (with carry), mul, similarity, hamming, polarity. Core identity: -1+1=0.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        op: {
          type: 'string',
          enum: ['neg', 'add', 'sub', 'mul', 'similarity', 'hamming', 'polarity'],
        },
        a: { ...tritArray, description: 'First trit vector.' },
        b: { ...tritArray, description: 'Second trit vector; required except neg/polarity.' },
      },
      required: ['op', 'a'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          op: { type: 'string' },
          result: {
            oneOf: [
              { type: 'array', items: { type: 'integer' } },
              { type: 'integer' },
              { type: 'number' },
            ],
          },
          note: { type: 'string' },
        },
        required: ['op', 'result'],
      },
      render: text,
    },
    async execute(args) {
      const { op, a, b } = args
      let result
      let note
      switch (op) {
        case 'neg':
          result = negateVector(a)
          break
        case 'add':
          result = addVectors(a, b)
          break
        case 'sub':
          result = addVectors(a, negateVector(b))
          break
        case 'mul':
          result = mulVectors(a, b)
          break
        case 'similarity': {
          const n = Math.min(a.length, b.length)
          result = a.slice(0, n).reduce((sum, v, i) => sum + v * b[i], 0)
          note = 'range -n..n where n = min length'
          break
        }
        case 'hamming': {
          const n = Math.min(a.length, b.length)
          result = a.slice(0, n).reduce((sum, v, i) => sum + (v !== b[i] ? 1 : 0), 0)
          break
        }
        case 'polarity':
          result = a.reduce((sum, v) => sum + v, 0)
          break
        default:
          throw new Error(`unknown operation: ${op}`)
      }
      return note === undefined ? { op, result } : { op, result, note }
    },
  }))

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_state',
    description: 'Navigate the 19683-state space: mirror (negate all trits), neighbors (up to 18), distance, path, path_through_void (reset via the all-EMPTY center 9841).',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        action: {
          type: 'string',
          enum: ['mirror', 'neighbors', 'distance', 'path', 'path_through_void'],
        },
        a: indexField,
        b: indexField,
      },
      required: ['action', 'a'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          action: { type: 'string' },
          from: integer,
          to: integer,
          mirror: integer,
          neighbors: { type: 'array', items: integer },
          neighbor_count: integer,
          distance: integer,
          steps: { type: 'array', items: integer },
          length: integer,
          via_void: { type: 'boolean' },
        },
        required: ['action'],
      },
      render: text,
    },
    async execute(args) {
      const { action, a, b } = args
      assertIndex(a, 'a')
      switch (action) {
        case 'mirror': {
          const mirror = MAX_INDEX - a
          return { action, from: a, mirror }
        }
        case 'neighbors': {
          const list = neighbors(a)
          return { action, from: a, neighbors: list, neighbor_count: list.length }
        }
        case 'distance': {
          assertIndex(b, 'b')
          return { action, from: a, to: b, distance: distance(a, b) }
        }
        case 'path': {
          assertIndex(b, 'b')
          const steps = pathBetween(a, b)
          return { action, from: a, to: b, steps, length: steps.length }
        }
        case 'path_through_void': {
          assertIndex(b, 'b')
          const first = pathBetween(a, CENTER)
          const second = pathBetween(CENTER, b)
          const steps = [...first, ...second.slice(1)]
          return { action, from: a, to: b, steps, length: steps.length, via_void: true }
        }
        default:
          throw new Error(`unknown action: ${action}`)
      }
    },
  }))

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_third_choice',
    description: 'Resolve a conflict between two states: void opposing dimensions to EMPTY while preserving agreement (-1+1=0 as a decision strategy); returns void and dominance candidates.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        a: indexField,
        b: indexField,
      },
      required: ['a', 'b'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          conflict: {
            type: 'object',
            additionalProperties: false,
            properties: {
              has_conflict: { type: 'boolean' },
              is_extreme_conflict: { type: 'boolean' },
              conflict_dims: { type: 'array', items: integer },
            },
            required: ['has_conflict', 'is_extreme_conflict', 'conflict_dims'],
          },
          candidates: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                strategy: { type: 'string' },
                state: integer,
                symbol: { type: 'string' },
                region: { type: 'string' },
                polarity: integer,
                voided_dims: { type: 'array', items: integer },
                preserved_dims: { type: 'array', items: integer },
                total_score: { type: 'number' },
                equidistance_score: { type: 'number' },
                void_ratio: { type: 'number' },
              },
              required: ['strategy', 'state', 'symbol', 'region', 'polarity', 'voided_dims', 'preserved_dims', 'total_score', 'equidistance_score', 'void_ratio'],
            },
          },
          recommended: { type: 'string' },
        },
        required: ['conflict', 'candidates', 'recommended'],
      },
      render: text,
    },
    async execute(args) {
      const { conflict, candidates } = thirdChoiceCandidates(args.a, args.b, labels)
      return {
        conflict,
        candidates,
        recommended: candidates[0]?.strategy ?? 'none',
      }
    },
  }))

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_decide',
    description: 'Dual-system decision (Kahneman S1/S2). System 1 cascade: exact hash → k-NN in 9D (give state) → fuzzy text; a confident S1 hit returns instantly (system: "s1") and saves tokens. A miss returns needs_s2: true — deliberate as System 2, then feed the outcome back through the feedback field (state/action/success) so it is learned into System 1 (school → internalize → graduate). mode: auto | system1 (fast only, never escalates) | system2 (always deliberate).',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        query: { type: 'string', description: 'The decision/input text, e.g. the user question or task.' },
        state: indexField,
        mode: {
          type: 'string',
          enum: ['auto', 'system1', 'system2'],
          description: 'auto = cascade; system1 = fast path only; system2 = always deliberate.',
        },
        feedback: {
          type: 'object',
          additionalProperties: false,
          description: 'S2 outcome to learn into System 1 (optional): the decided state, chosen action, and whether it succeeded.',
          properties: {
            state: { ...indexField, description: 'The System 2 decision state index.' },
            action: { type: 'string', description: 'What was decided/done.' },
            success: { type: 'boolean', description: 'Whether the outcome was positive.' },
          },
          required: ['state'],
        },
      },
      required: ['query'],
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          system: { type: 'string' },
          stage: { type: 'string' },
          needs_s2: { type: 'boolean' },
          pattern: patternSchema,
          similarity: { type: 'number' },
          candidates: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                distance: { type: 'number' },
                state_index: integer,
                confidence: { type: 'number' },
                interpretation: interpretationSchema,
              },
              required: ['distance', 'state_index', 'confidence', 'interpretation'],
            },
          },
          learned: { type: 'boolean' },
          coverage: { type: 'number' },
          pattern_count: integer,
        },
        required: ['system', 'stage', 'needs_s2', 'coverage', 'pattern_count'],
      },
      render: text,
    },
    async execute(args) {
      const statsBefore = s1.stats()
      let learned = false
      if (args.feedback?.state !== undefined) {
        s1.learn(args.query, args.feedback.state, args.feedback.action ?? '', args.feedback.success !== false)
        s1.save(patternsPath)
        learned = true
      }

      const mode = args.mode ?? 'auto'
      const coverage = s1.stats().coverage
      const patternCount = s1.patterns.length

      if (mode === 'system2') {
        return { system: 's2', stage: 'deliberate', needs_s2: true, learned, coverage, pattern_count: patternCount }
      }

      // 1. exact hash
      const exact = s1.matchExact(args.query)
      if (exact) {
        return { system: 's1', stage: 'exact', needs_s2: false, pattern: withInterpretation(exact), learned, coverage, pattern_count: patternCount }
      }

      // 2. k-NN in 9D (only when the model supplies a projected state)
      let candidates = []
      if (args.state !== undefined) {
        const knn = s1.matchKnn(args.state, 3)
        candidates = knn.map(k => ({
          distance: round4(k.distance),
          state_index: k.pattern.state_index,
          confidence: round4(k.pattern.confidence),
          interpretation: interpret(k.pattern.state_index, labels),
        }))
        if (knn.length && knn[0].distance <= KNN_DISTANCE_THRESHOLD && knn[0].pattern.confidence >= KNN_CONFIDENCE_THRESHOLD) {
          return { system: 's1', stage: 'knn', needs_s2: false, pattern: withInterpretation(knn[0].pattern), candidates, learned, coverage, pattern_count: patternCount }
        }
      }

      // 3. fuzzy text
      const fuzzy = s1.matchFuzzy(args.query)
      if (fuzzy) {
        return { system: 's1', stage: 'fuzzy', needs_s2: false, pattern: withInterpretation(fuzzy.pattern), similarity: fuzzy.similarity, candidates, learned, coverage, pattern_count: patternCount }
      }

      return { system: 's2', stage: 'deliberate', needs_s2: true, candidates, learned, coverage, pattern_count: patternCount }
    },
  }))

  ctx.effect(() => ctx.tools.register({
    name: 'btcu_patterns',
    description: 'Graduation meter: how much the System 1 library has learned (pattern count, state coverage of the 19683 space, reuse/success stats, average confidence). Call periodically to track maturation.',
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {},
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          pattern_count: integer,
          covered_states: integer,
          coverage: { type: 'number' },
          total_reuses: integer,
          success_count: integer,
          success_rate: { type: 'number' },
          avg_confidence: { type: 'number' },
          top_states: { type: 'array', items: integer },
          path: { type: 'string' },
        },
        required: ['pattern_count', 'covered_states', 'coverage', 'total_reuses', 'success_count', 'success_rate', 'avg_confidence', 'top_states'],
      },
      render: text,
    },
    async execute() {
      return { ...s1.stats(), path: patternsPath }
    },
  }))
}
