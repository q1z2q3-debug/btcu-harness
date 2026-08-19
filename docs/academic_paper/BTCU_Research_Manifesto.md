# BTCU Research Manifesto: A Call for Collaborative Development

**Date**: August 18, 2026
**Series**: BTCU (Balanced Ternary Cognitive Universe)
**Repository**: https://github.com/q1z2q3-debug/btcu-harness
**Current Version**: v0.3
**Status**: Preliminary Research Stage

---

## 1. What This Is

BTCU is a research program exploring the hypothesis that **cognition can be understood through the lens of balanced ternary {-1, 0, +1} discrete state spaces**. It comprises seven papers proposing a theoretical framework, mathematical derivations, simulation experiments, and initial engineering implementations.

**This is not a finished theory. This is an open invitation.**

Every claim in this series carries an implicit prefix: "*If balanced ternary state spaces are a valid model of cognition, then...*" The "if" is large, and we do not yet know the answer.

---

## 2. What Each Paper Actually Claims (and Does Not Claim)

| Paper | Claims | Does NOT Claim | Confidence Level |
|-------|--------|----------------|----------------|
| **I. Ternary Cognitive Unit** | Balanced ternary is the minimal integer state space for directed transitions; Ball (2026) proved necessity | That human cognition actually uses ternary states | Theorem-proven (within stated axioms) |
| **II. Nine-Dimensional Space** | 9 independent cognitive dimensions × 3 values each yields 19,683 states; this space has natural geometric structure | That any specific 9 dimensions are the "right" ones; that the state count has biological significance | Mathematically self-consistent |
| **III. Encoding & Metrics** | The Hamming-like metric on this space measures cognitive distance; continuous values can be quantized | That the quantization preserves all information (compression ratio 16,725:1 without proven fidelity bound) | Self-consistent; quantization fidelity unverified |
| **IV. Mathematical Constants** | In this framework, π, e, γ emerge as eigenproperties of the dynamics | That these constants are "cognitive" in any ontological sense; that this derivation applies to real brains | Derived within framework; real-world mapping speculative |
| **V. Cognitive Capital & Token Economics** | Pattern reuse reduces inference cost exponentially; cost law C(t) = C₀e^(-αt) + C∞ is the steady-state solution | That this cost model matches real LLM API billing; that the 80% cost reduction scales to production | Simulation-based; real-world economics unverified |
| **VI. Cognitive Layer as Active Memory** | The cognitive layer encodes "attitudes" not "facts"; this differs from RAG/context window approaches | That BTCU memory is superior to RAG in real applications; that cognitive states can be reliably extracted from LLM outputs | Architectural argument; empirical superiority unproven |
| **VII. Cognitive Dynamics** | The Master Equation is the unique dynamics satisfying four axioms (conservation, locality, detailed balance, metric compatibility); it derives Papers IV-V as theorems | That real cognitive dynamics satisfies these axioms; that the Markov assumption holds for biological cognition | Mathematically rigorous within axioms; biological validity unknown |

**Summary**: Papers I-III are mathematical constructions (self-consistent). Papers IV-VII are theoretical physics within that construction (derived, not assumed). None have been validated against biological or deployed artificial cognition.

---

## 3. Known Limitations (The Honest List)

### 3.1 Mathematical Limitations

1. **Rate function inconsistency** (Paper VII §4.1): The initial rate function was replaced mid-derivation with a Metropolis form to satisfy detailed balance. A fully self-consistent derivation from first principles is pending.
2. **Markov assumption**: Real cognition has memory. The Master Equation assumes memoryless transitions. This is acknowledged but not resolved.
3. **Closed system assumption**: The Master Equation treats the agent as isolated. Real agents continuously receive information from the environment. The open-system extension is future work.
4. **Learning is external**: The transition rates are fixed. Learning (rate modification) is not part of the dynamics. This is the single largest gap.

### 3.2 Empirical Limitations

5. **No biological data**: No fMRI, EEG, or behavioral experiment has been conducted to test whether human cognition exhibits ternary-state transitions.
6. **No real deployment data**: The token economy (Paper V) is a simulation. The 80% cost reduction has not been measured on a production agent.
7. **Cognitive state extraction is manual**: In the current implementation, cognitive states are assigned by human annotation. An automatic extractor from LLM outputs or neural activity does not yet exist.
8. **Quantization fidelity unproven**: The mapping from 224×224 RGB images (150,528 dimensions) to 9-dimensional ternary states has no proven information-theoretic bound on fidelity loss.

### 3.3 Theoretical Limitations

9. **The 9 dimensions are postulated, not derived**: Why 9? Why not 7 or 12? The choice is motivated by cognitive phenomenology (perception, emotion, reasoning, etc.) but not derived from deeper principles.
10. **The energy landscape is undefined**: What is "cognitive energy"? It is a Lagrange multiplier in the Master Equation derivation, but its physical or psychological meaning is unspecified.
11. **No multi-agent extension**: The framework is single-agent. Multi-agent interaction, social cognition, and collective dynamics are entirely unaddressed.

---

## 4. What We Need From the Community

This series is published as a **preliminary research artifact** specifically to invite community participation in filling these gaps. We are looking for collaborators in the following areas:

### 4.1 Empirical Validation (Highest Priority)

**Goal**: Test whether real cognition (human or artificial) exhibits the predicted dynamics.

**Specific asks**:
- **Neuroscientists**: Can neural population activity be coarse-grained into ternary states? Does the transition statistics match the Master Equation predictions?
- **Psychologists**: Can human decision-making tasks be designed to test for the predicted π-periodic reflection cycles or e-exponential cost decay?
- **Engineers**: Can the BTCU cognitive layer be integrated into a deployed agent (LangChain, AutoGPT, etc.) and benchmarked against baseline memory approaches?

### 4.2 Mathematical Refinement

**Goal**: Fix the known formal gaps.

**Specific asks**:
- **Mathematical physicists**: Provide a self-consistent derivation of the rate function that does not require mid-derivation replacement.
- **Statisticians**: Prove or disprove the information fidelity of the 150,528 → 9 dimensionality reduction.
- **Probability theorists**: Extend the Master Equation to non-Markovian processes (e.g., via path integrals or fractional calculus).

### 4.3 Theoretical Extension

**Goal**: Push the framework into new domains.

**Specific asks**:
- **Cognitive scientists**: Propose alternative dimension sets and test whether they yield better predictive power.
- **Philosophers of mind**: Evaluate the ontological status of "cognitive energy" and the 19,683-state ontology.
- **Multi-agent systems researchers**: Extend the Master Equation to interacting agents (Ising-like coupling?).

### 4.4 Engineering & Open Source

**Goal**: Make the framework usable by practitioners.

**Specific asks**:
- **ML engineers**: Build an automatic cognitive-state extractor from LLM hidden states or attention patterns.
- **DevOps engineers**: Containerize the BTCU harness for easy deployment.
- **Technical writers**: Improve documentation, tutorials, and API references.

---

## 5. How to Contribute

### 5.1 Immediate Actions (No Barrier to Entry)

1. **Read the papers** and open GitHub Issues with questions, corrections, or counterarguments.
2. **Run the simulations** (`verify_theorems.py`, `experiment_void_advantage.py`) and report whether you can reproduce the results.
3. **Propose alternative formulations** for any of the 11 limitations listed above.

### 5.2 Medium-Term Contributions

1. **Write a missing paper** from the roadmap (Paper VIII: Empirical Validation; Paper X: Cognitive Biases; etc.). We will link to it from the main repository.
2. **Build an integration**: Connect BTCU to LangChain, AutoGPT, or another agent framework and publish benchmark results.
3. **Design an experiment**: Propose a behavioral or neuroscientific experiment that could test a BTCU prediction.

### 5.3 Governance

- The repository is MIT-licensed. All contributions are welcome.
- For significant theoretical contributions (new papers, major theorem proofs), we encourage co-authorship.
- The project is currently maintained by q1z2q3. If community interest grows, we will transition to a more formal governance structure.

---

## 6. Our Commitment

As the authors, we commit to:

1. **Honesty**: We will not overstate claims. Every paper will clearly distinguish between "proven within the framework" and "hypothesized to apply to real cognition."
2. **Responsiveness**: We will respond to Issues and PRs within 7 days.
3. **Attribution**: We will properly credit all contributors, whether through co-authorship, acknowledgments, or repository mentions.
4. **Openness**: We will not patent core theoretical components. The mathematics belongs to the community.

---

## 7. The Bottom Line

BTCU is currently a **self-consistent mathematical theory** with **ambitious empirical aspirations** and **significant unverified claims**.

We believe the framework has enough internal coherence and novelty to warrant community attention. But we do not believe it has enough empirical validation to warrant uncritical acceptance.

**If you are a skeptic, we welcome your criticism.** The fastest way to improve this work is to find its breaking points.

**If you are a builder, we welcome your implementations.** The fastest way to validate this work is to deploy it and measure the results.

**If you are a theorist, we welcome your refinements.** The fastest way to deepen this work is to fix its formal gaps.

This manifesto is a standing invitation. The papers are a starting point, not a destination.

---

**Published**: August 18, 2026
**License**: CC-BY-4.0
**Contact**: q1z2q3@126.com
**Repository**: https://github.com/q1z2q3-debug/btcu-harness

> "The map is not the territory. But a bad map is better than no map, provided we know it's a map."
