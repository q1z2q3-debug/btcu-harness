Balanced Ternary by Necessity The Minimal Integer State Space for Directed Transitions 

Alan Ball ORCID: 0009-0008-6298-0661 alan@caelix.co.uk https://caelix.co.uk February 27, 2026 

## **Abstract** 

It is a standard, often unexamined assumption that a binary system is the minimal foundational alphabet for representing state transitions. We demonstrate that this assumption is structurally incomplete. 

We ask a foundational question: what is the smallest integer-valued state space capable of intrinsically representing a directed temporal transition, without relying on an extrinsic observer or sign convention? Starting from no physical assumptions, we impose three logical constraints on any candidate state space: it must contain a neutral ground state, support a directed transition away from that ground state, and be closed under the inverse of that transition on all states reachable from 0 by a single step. 

We show that the binary set _{_ 0 _,_ 1 _}_ strictly fails this closure requirement. Instead, these constraints uniquely and necessarily determine the balanced-ternary set _S_ = _{−_ 1 _,_ 0 _,_ +1 _}_ . No smaller set works without importing an external rule; no larger finite set is required. This establishes balanced ternary not as a design choice, but as the unavoidable logical minimum for directed transitions. 

## **Reading guide** 

This paper makes a single, narrow argument: that _{−_ 1 _,_ 0 _,_ +1 _}_ is not a design choice but a logical necessity, given three constraints any representation of a directed temporal transition must satisfy. 

For the philosophical motivation of the “first directed distinction” framing, see: 

Alan Ball, _On the Necessity of Existence_ (Zenodo, 2026), DOI: 10.5281/zenodo.18797375 

The argument is self-contained. The logical argument occupies Sections 1–4. Section 5 clarifies scope and implications. 

The argument turns on showing that binary state spaces cannot represent direction intrinsically, while _{−_ 1 _,_ 0 _,_ +1 _}_ can. 

## **1 The problem: minimal intrinsic representation** 

A recurring discipline in this paper is the distinction between _intrinsic_ and _extrinsic_ structure. 

A property is intrinsic if it follows from the state space alone. It is extrinsic if it requires a convention, a label, or additional information imposed from outside. 

We ask the following question. 

## **The minimal representation problem:** 

What is the smallest integer-valued set _S_ such that a directed temporal transition can be represented using only the elements of _S_ , with no external convention required to recover the direction? 

**Physical intuition (The road with no sign posts):** Imagine a road with two towns on it. If the towns are labelled only _A_ and _B_ , you cannot tell from the labels alone which direction is forward. You need a sign post, a convention, an outside observer, something extra. The question we are asking is: can we label the towns in a way that makes the direction self-evident, using the smallest possible alphabet of labels? The answer is yes, and the alphabet turns out to have exactly three symbols. 

To solve this minimal representation problem, we cannot simply pick symbols that look convenient. A transition requires a starting line. A directed jump requires a destination. And most importantly, if the representation is truly self-contained, undoing that jump cannot force us to introduce a new symbol that was not already present. We formalise this as three constraints. 

- **Constraint G (Ground state).** _S_ must contain a distinguished neutral element 0, representing the prior state before any transition has occurred. A transition requires an origin; the origin must be a member of _S_ . 

- **Constraint T (Transition).** _S_ must contain at least one element _e ̸_ = 0 reachable from 0 by a single directed step. We call this element the _unit excitation_ and write the transition 0 _→ e_ . 

- **Constraint C (Closure).** _S_ must be closed under the inverse of the transition operator for all states reachable from 0 by a single step. That is, if _τ_ : _x �→ x_ + _e_ represents one forward step and _τ[−]_[1] : _x �→ x − e_ its inverse, then for every _x ∈ S_ with _x ∈{_ 0 _, e, −e}_ we must have _τ[−]_[1] ( _x_ ) _∈ S_ . 

Constraint C is the critical one. It encodes the requirement that the state space is self-contained: the inverse transition does not require the introduction of new symbols not already in _S_ . Without it, the representation is open-ended and must be closed by an external decision. 

## **2 The binary case fails** 

The natural candidate for a minimal state space is the binary set _B_ = _{_ 0 _,_ 1 _}_ . It satisfies Constraint G (contains 0) and Constraint T (contains 1, reachable from 0 by 0 _→_ 1). We now show it fails Constraint C. 

**Physical intuition (The traffic-light problem):** Consider a red light and a green light. They are mutually exclusive: only one may be on at a time. If you encode the system with only two labels, _A_ and _B_ , you can say which lamp is lit, but you have not encoded a notion of “forward”. The arrow of time then lives in an external rule (“it alternates”) or in the observer’s memory of the last transition. To make direction intrinsic, you need a neutral moment: both lamps off. At that ground state there is no intrinsic fact about whether the next committed state will be red or green without additional information. Introducing an explicit ground state 0 and two opposed departures from it is the minimal way to carry direction in the state space itself rather than in memory. 

## **Proposition:** 

The binary set _B_ = _{_ 0 _,_ 1 _}_ with unit excitation _e_ = 1 does not satisfy Constraint C. 

## **Proof:** 

The inverse transition operator is _τ[−]_[1] : _x �→ x −_ 1. Applying _τ[−]_[1] to the ground state: 


![](media/balanced_ternary_by_necessity.pdf-0003-07.png)


But _−_ 1 _∈/ B_ . Therefore _B_ is not closed under _τ[−]_[1] . To close the space, we must either add _−_ 1 to _S_ , or impose an external rule identifying _−_ 1 with some existing element of _B_ . The only existing element available for this identification is 0 itself (since identifying _−_ 1 with 1 would collapse the distinction between a forward and a backward step, destroying Constraint T). But identifying _−_ 1 with 0 means the inverse of a forward step from 0 returns to 0, which makes the transition cycle 0 _→_ 1 _→_ 0 rather than the directed sequence 0 _→_ 1. In a cycle, the notions of forward and backward are not intrinsically distinguishable from the state labels alone: both transitions look like “moving to the other state.” The direction must then be supplied extrinsically, violating our requirement. □ 

The binary case can be made to work, but only by importing an extrinsic convention: a rule that says “the direction of positive time is 0 _→_ 1, not 1 _→_ 0.” This is precisely the kind of external imposition the minimal representation problem forbids. 

## **3 The ternary case succeeds** 

Adding the element _−_ 1 to _B_ yields _S_ = _{−_ 1 _,_ 0 _,_ +1 _}_ . We now show this set satisfies all three constraints and that the direction of time becomes intrinsic to the structure. 

**Physical intuition (The number line with a centre):** Place three points on a line: _−_ 1 on the left, 0 in the centre, +1 on the right. The centre point is special: it is the only one equidistant from both others. A transition from 0 to +1 is self-evidently rightward. A transition from 0 to _−_ 1 is self-evidently leftward. You do not need a sign post because the geometry of the three points itself encodes the direction. The asymmetry is intrinsic. 

## **Proposition:** 

The balanced-ternary set _S_ = _{−_ 1 _,_ 0 _,_ +1 _}_ with unit excitation _e_ = +1 satisfies all three constraints. 

## **Verification:** 

- **Constraint G.** 0 _∈ S_ . ✓ 

- **Constraint T.** 0 + 1 = +1 _∈ S_ . ✓ 

- **Constraint C.** We must check that _τ[−]_[1] ( _s_ ) = _s −_ 1 _∈ S_ for all states reachable from 0 by at most one step: 


![](media/balanced_ternary_by_necessity.pdf-0004-09.png)


Both are in _S_ . 

This requires a clarification of scope. Constraint C is a single-step closure condition: it requires that the inverse of a single forward step from the ground state, and from any state reachable from the ground state in one step, lands back inside _S_ . 

States beyond _{−_ 1 _,_ 0 _,_ +1 _}_ correspond to multi-step compositions and are outside the minimal representation problem considered here. 

We also note a structural property that does not hold for _{_ 0 _,_ 1 _}_ but does hold for _{−_ 1 _,_ 0 _,_ +1 _}_ : 

## **Additive symmetry:** 

For all _s ∈ S_ , _−s ∈ S_ . That is, _S_ is closed under negation. This guarantees that the forward and inverse transitions are exact algebraic duals. The sign structure is not a convention: it is baked into the algebra of _S_ itself. 

## **4 Uniqueness: why not a larger set?** 

Having shown that _{−_ 1 _,_ 0 _,_ +1 _}_ satisfies all three constraints, we now show it is the _unique minimal_ such set. 

**Physical intuition (Goldilocks and the state space):** We have shown that two states are too few: they cannot carry direction intrinsically. Could four states buy anything that three cannot? Could we use three states arranged differently, say _{_ 0 _,_ 1 _,_ 2 _}_ ? We will show this fails for the same reason _{_ 0 _,_ 1 _}_ fails: it cannot encode direction without an extrinsic convention. Three is not just sufficient; it is exactly right. 

## **Proposition:** 

_S_ = _{−_ 1 _,_ 0 _,_ +1 _}_ is the unique minimal integer-valued set satisfying Constraints G, T, and C together with additive symmetry. 

## **Proof:** 

We showed in Section 2 that _|S|_ = 2 is insufficient. So _|S| ≥_ 3. 

Now consider any three-element integer set satisfying Constraint G. It must contain 0. By Constraint T it must contain some _e ̸_ = 0; by convention take _e >_ 0 (the argument is symmetric for _e <_ 0). The smallest such _e_ is 1, giving us _{_ 0 _,_ 1 _,_ ? _}_ . 

By Constraint C, _τ[−]_[1] (0) = 0 _−_ 1 = _−_ 1 must be in _S_ . So the third element is forced to be _−_ 1, giving _{−_ 1 _,_ 0 _,_ 1 _}_ . 

No other choice of third element works: 

- Choosing any integer _k >_ 1 as the third element leaves _−_ 1 outside _S_ , violating Constraint C. 

- Choosing _e_ = 2 instead of _e_ = 1 gives _{−_ 2 _,_ 0 _,_ 2 _}_ after applying C, which is simply _{−_ 1 _,_ 0 _,_ +1 _}_ rescaled by 2. It is isomorphic, not distinct. 

For _|S| >_ 3: any set with four or more elements contains states that cannot be reached from 0 by a single application of _τ_ or _τ[−]_[1] . Such states are not required by the single-step transition representation. They may be introduced for other purposes, but they are not minimal. Therefore _{−_ 1 _,_ 0 _,_ +1 _}_ is the unique minimal solution up to rescaling. □ 

The non-symmetric candidate _{_ 0 _,_ 1 _,_ 2 _}_ deserves explicit treatment. It satisfies Constraints G and T but fails Constraint C: _τ[−]_[1] (0) = _−_ 1 _∈{/_ 0 _,_ 1 _,_ 2 _}_ . To close it, we would need to identify _−_ 1 with one of the existing elements, which reintroduces the problem of extrinsic convention. It also lacks additive symmetry: _−_ 1 _∈{/_ 0 _,_ 1 _,_ 2 _}_ and _−_ 2 _∈{/_ 0 _,_ 1 _,_ 2 _}_ , so the set is not closed under negation. Direction in _{_ 0 _,_ 1 _,_ 2 _}_ is therefore a matter of convention, not structure. 

## **5 Discussion** 

The argument presented here is deliberately narrow. It claims one thing: that if you want to represent a directed temporal transition using an integer-valued state space without importing any external convention, you are forced to use _{−_ 1 _,_ 0 _,_ +1 _}_ . 

This narrowness is a feature. Foundational work often fails by claiming too much and therefore proving nothing rigorously. The claim here is modest enough to be precise and precise enough to be falsifiable. 

## **Scope:** 

The result proven in this paper is purely structural: given the three stated constraints, the unique minimal integer-valued state space capable of intrinsically representing a single directed transition is _{−_ 1 _,_ 0 _,_ +1 _}_ . No further interpretation is assumed or required. 

## **Relationship to existing work:** 

The observation that _{−_ 1 _,_ 0 _,_ +1 _}_ is the minimal signed integer set is not new in isolation. What is new is the framing: deriving it from the logical requirements of a directed transition representation rather than presenting it as a design choice motivated by computational efficiency or numerical convenience. 

## **Open question:** 

The argument establishes necessity for the one-dimensional case: a single directed transition along a single axis. What additional structural assumptions are required to extend this argument to richer mathematical objects (additional axes, invariants, and constants) is outside the scope of this paper. 

## **6 Conclusion** 

The balanced-ternary state space _{−_ 1 _,_ 0 _,_ +1 _}_ is not a modelling choice. It is the unique minimal integer-valued set that can represent a directed temporal transition without importing an extrinsic sign convention. 

The argument rests on three constraints: the existence of a neutral ground state, the existence of a directed unit transition away from it, and closure of the state space under the inverse of that transition. Binary sets fail the third constraint and can represent direction only with an external convention. The balanced-ternary set satisfies all three, is additively symmetric, and is minimal in the sense that no proper subset satisfies all constraints and no extension is required. 

Whether this algebraic necessity has deeper implications beyond the minimal representation problem remains an open question. What is established here is the narrower claim: the balanced-ternary state space is the only integer-valued alphabet consistent with intrinsic directionality and minimal complexity. What this alphabet produces when subjected to further structural operations is a question this paper deliberately leaves open. 

