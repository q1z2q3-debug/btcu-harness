## Constants From Balanced Ternary 

The Forced Arithmetic of _{−_ 1 _,_ 0 _,_ +1 _}_ 

Alan Ball ORCID: 0009-0008-6298-0661 alan@caelix.co.uk https://caelix.co.uk February 28, 2026 

## **Abstract** 

The companion paper _Balanced Ternary by Necessity_ established that _{−_ 1 _,_ 0 _,_ +1 _}_ is the unique minimal integer-valued state space capable of intrinsically representing a directed transition. This paper asks the next question: what mathematical structure appears when that alphabet is subjected to successive completion demands beyond its primitive one-step content? 

Starting from _{−_ 1 _,_ 0 _,_ +1 _}_ , we construct a derivation ladder. Some constants arise once independent generators, metric comparison and symmetry-preserving operators are admitted. Others appear only when the substrate is examined through increasingly strong analytical completions, including recurrence, refinement, rotation and summation. The claim of this paper is therefore ordered rather than absolute: the constants are not all primitive contents of the ternary alphabet, but they do appear in a strict sequence once each additional structural demand is made explicit. 

No physical assumption is made at any step. Mathematical structure is introduced only when required, and each constant enters at the earliest stage permitted by the available machinery. The result is a disciplined map from a minimal discrete substrate to the hierarchy of irrational and transcendental constants naturally exposed by its admissible completions. 

## **Reading guide** 

This paper is the third in a sequence. 

The philosophical argument for why anything exists at all is given in: 

Alan Ball, _On the Necessity of Existence_ (Zenodo, 2026), DOI: 10.5281/zenodo.18797375 

The formal proof that _{−_ 1 _,_ 0 _,_ +1 _}_ is the unique minimal state space for directed transitions is given in: 

Alan Ball, _Balanced Ternary by Necessity_ (Zenodo, 2026), DOI: 10.5281/zenodo.18806015 

This paper begins where that proof ends. It takes the established alphabet and asks what happens when you operate on it. Each section derives one or more constants. The derivation chain is sequential: each result depends only on results already established. 

This paper is deliberately silent on physical interpretation. 

While the reader may notice correspondences; 

This paper does not comment on them. 

## **I. The Geometry of the Alphabet** 

## **1 The second axis and the quarter-turn** 

**Starting inventory:** _{−_ 1 _,_ 0 _,_ +1 _}_ on a single axis with generator _e_ and transition operators _τe_ and _τe[−]_[1][.] 

## **The question:** 

Can a second directed transition exist that is independent of the first? 

## **The requirement:** 

Let _f_ denote a second generator with the same single-step contract as _e_ , but not reducible to _±e_ by rescaling or relabelling. We call this requirement _independence_ . 

Independence alone yields a copy of Z[2] . But this by itself does not distinguish a plane from an arbitrary product of two lines. 

To obtain an intrinsic notion of “right angle” without importing any physical geometry, we require the existence of a structure-preserving quarter-turn operator _J_ acting on the span of the generators such that 

**==> picture [108 x 12] intentionally omitted <==**

This implies _J_[2] ( _e_ ) = _−e_ and _J_[2] ( _f_ ) = _−f_ , hence _J_[2] = _−_ 1 on the generator subspace. 

## **The result:** 

A second independent axis by itself does not force an operator whose square is negation. What forces it is the additional demand that the two-generator extension admit an intrinsic, structure-preserving quarter-turn. 

Under that demand, _[√] −_ 1 enters as a purely structural object: not as a number imported from elsewhere, but as the unique algebraic witness of a quarter-turn that cannot be realised on a single signed line. 

With this operator, the natural integer-coordinate plane is Z[ _i_ ] (the Gaussian integers), where _i_ denotes the action of _J_ and _i_[2] = _−_ 1. 

**Inventory update:** _{−_ 1 _,_ 0 _,_ +1 _}_ , two independent generators _e_ and _f_ , the operator _J_ with _J_[2] = _−_ 1. 

**==> picture [43 x 12] intentionally omitted <==**

## **2 The diagonal and** _√_ 2 

## **The question:** 

What is the distance of the diagonal step _e_ + _f_ on the plane? 

## **The requirement:** 

To answer this, we need a notion of length. We impose the minimal structural requirement: the existence of an intrinsic quadratic invariant preserved by the quarter-turn _J_ . 

Concretely, assume there exists a function _∥· ∥_ on the integer span of _{e, f }_ such that: 

(i) _∥e∥_ = _∥f ∥_ (axis symmetry), 

(ii) _∥J_ ( _v_ ) _∥_ = _∥v∥_ (quarter-turn invariance), 

(iii) _∥v∥_[2] is a quadratic form compatible with additivity and negation. 

These conditions determine, up to an overall scale, the Euclidean form 

**==> picture [105 x 14] intentionally omitted <==**

We fix the overall scale by choosing units such that _∥e∥_ = _∥f ∥_ = 1. With this normalisation, the diagonal step _e_ + _f_ satisfies: 

**==> picture [293 x 14] intentionally omitted <==**

## **The result:** 

_√_ 2 is not an imported constant. It is the first unavoidable irrational that appears once a plane supports two independent unit steps together with an intrinsic quarter-turn preserving a quadratic invariant. 

The substrate has asked a question about its own geometry and received an answer it cannot express as a ratio of integers. 

~~_√_~~ 2 = 1 _._ 41421356 _. . ._ 

## **3 The third axis and** _√_ 3 

## **The question:** 

Can a third directed transition exist that is independent of both _e_ and _f_ ? 

## **The requirement:** 

We introduce a third generator _g_ , independent of both _e_ and _f_ , with the same single-step contract. As an additional structural assumption, we require that each coordinate plane admits a structure-preserving quarter-turn symmetry, mirroring the 2D case. 

This extends the reachability set from Z[2] to Z[3] . The quarter-turn requirement in each coordinate plane yields three operators: 

**==> picture [105 x 15] intentionally omitted <==**

with actions such as _Jef_ ( _e_ ) = _f_ , _Jef_ ( _f_ ) = _−e_ , and similarly for the other pairs. 

The unit-cube diagonal step _e_ + _f_ + _g_ now has: 

**==> picture [326 x 14] intentionally omitted <==**

## **The result:** 

The unit-cube diagonal of the minimal three-axis integer-coordinate space has length _√_ 3. 

We also note: in three dimensions, the quarter-turn operators _Jef_ , _Jfg_ , _Jge_ do not commute under composition. The smallest consistent algebra that accommodates three pairwise plane-rotation quarter-turn generators is quaternionic in character. This paper does not develop the quaternionic structure further; it notes only that it is forced by the extension from two axes to three. 

**==> picture [97 x 12] intentionally omitted <==**

## **4 The first non-trivial integer-coordinate distance and** _√_ 5 

## **The question:** 

What integer-coordinate distances exist beyond the axis, the unit-square diagonal, and the unit-cube diagonal? 

## **The requirement:** 

The integer-coordinate space Z[3] contains all integer-coordinate vectors. The squared distances from the origin are of the form _a_[2] + _b_[2] + _c_[2] for integers _a, b, c_ . 

The first few distinct squared distances are: 

**==> picture [120 x 10] intentionally omitted <==**

Squared distance 4 is simply 2[2] : a two-step axis move. It is the first composite. Squared distance 5 is the first that introduces a genuinely new irrational. It is realised by any integer vector of the form (1 _,_ 2 _,_ 0) or its permutations and sign changes. 

**==> picture [241 x 14] intentionally omitted <==**

## **The result:** 

_√_ 5 is the shortest integer-coordinate distance that cannot be reduced to a multiple of the axis length, the unit-square diagonal, or the unit-cube diagonal. 

~~_√_~~ 5 = 2 _._ 23606797 _. . ._ 

## **II. The Self-Referential Constants** 

## **5 The golden ratio** _φ_ 

## **The question:** 

What appears when the integer sequence is subjected to a simple, self-referential additive recurrence? 

## **The derivation:** 

The integers Z support integer sequences and therefore many possible recurrences. Not all of them are equally informative. Constant, periodic or purely sign-flipping recurrences remain too degenerate to drive a genuine growth law. To obtain a non-trivial self-referential rule using only addition of previously available terms, we choose the recurrence 

**==> picture [129 x 12] intentionally omitted <==**

This is the Fibonacci recurrence. It is not claimed here that this choice is the only recurrence the integers permit. It is claimed that it is a highly natural and minimal additive recurrence once one asks for non-degenerate growth built from prior terms alone. 

Its characteristic equation is: 

**==> picture [254 x 25] intentionally omitted <==**

The positive root is the golden ratio: 

**==> picture [58 x 25] intentionally omitted <==**

This is the asymptotic growth rate of the sequence. It is also the unique positive number satisfying _φ_ = 1 + 1 _/φ_ : the ratio that is self-similar under decomposition into itself plus unity. 

## **The result:** 

_φ_ is not imported. It appears as the growth rate of a chosen but highly natural non-trivial additive recurrence on the integers, and it is built from _√_ 5, which was itself exposed by the integer-coordinate geometry. 

**==> picture [139 x 25] intentionally omitted <==**

## **6 The natural exponential** _e_ 

## **The question:** 

What appears once the unit step is examined through arbitrary refinement and compounded growth? 

## **The derivation:** 

The substrate has a unit transition of magnitude 1. By itself, this does not yet contain continuous growth. To reach that regime, an additional completion demand must be admitted: the unit step is allowed to be refined into _n_ equal sub-steps, each of magnitude 1 _/n_ , while preserving the same total action. 

If growth compounds multiplicatively at each refined sub-step, the accumulated factor after _n_ such steps is 

As _n →∞_ , this converges: 

**==> picture [93 x 67] intentionally omitted <==**

The point is not that the primitive ternary alphabet is already “doing” infinite subdivision. The point is that, once refinement is admitted as an analytical completion of the unit step, this limit is no longer optional. It is the unique invariant associated with maximal compounding under arbitrary equal subdivision. 

## **The result:** 

_e_ is the natural base of continuous growth exposed when a discrete unit transition is carried through the completion demand of arbitrary refinement. 

**==> picture [87 x 9] intentionally omitted <==**

## **7 The half-period** _π_ 

## **The question:** 

What constant appears once the previously established objects _i_ and _e_ are carried through a rotation-based analytical completion? 

## **The derivation:** 

We have established the complex plane Z[ _i_ ] and the exponential function _e[x]_ . By themselves, these do not yet compel a circle. To reach that regime, an additional completion demand must be admitted: imaginary exponents are allowed, so that the exponential is examined along the purely imaginary direction _it_ . 

Under that demand, the standard power-series expansion gives 

**==> picture [141 x 31] intentionally omitted <==**

where cos _t_ and sin _t_ are defined by the even and odd parts of the same series. This turns the exponential into a rotation-valued object on the complex plane. 

The function _e[it]_ starts at 1 when _t_ = 0. It first returns to the real axis on the negative side when _e[it]_ = _−_ 1. The value of _t_ at which this occurs is _π_ . 

_π_ is therefore the half-period of unit rotation once the earlier algebraic machinery is carried through this rotational completion. It is not being claimed that raw ternary syntax already contains a physical circle. It is being claimed that, once the complex exponential is admitted, the half-period is no longer optional. It is the unique real number satisfying 

**==> picture [43 x 11] intentionally omitted <==**

There is a second, corroborating route to the same constant. On the integer grid Z[2] , count the number of integer points inside a circle of radius _r_ . In the limit of large _r_ , the ratio of this count to _r_[2] converges to _π_ . This does not make the circle primitive; it shows that once rotation-invariant comparison is admitted, the same constant reappears through lattice counting. 

## **The result:** 

_π_ is the half-period of the unit rotation exposed when the already established objects _i_ and _e_ are carried through a rotational analytical completion. 

**==> picture [89 x 8] intentionally omitted <==**

## **III. The Convergence** 

## **8 Euler’s identity** 

The five quantities 0, 1, _e_ , _i_ , and _π_ have been derived independently: 

- 0: the ground state (Paper 2, Constraint G). 

- 1: the unit excitation (Paper 2, Constraint T). 

- _i_ : the quarter-turn witness (Section 1). 

- _e_ : the limit of unit compounding (Section 6). 

- _π_ : the half-period of unit rotation (Section 7). 

They satisfy: 

**==> picture [53 x 12] intentionally omitted <==**

This is not a coincidence and not a construction. It is a constraint: the five objects derived from the substrate are not independent of one another. They are locked together by the algebra that produced them. 

The substrate’s constants form a closed system. 

**==> picture [53 x 11] intentionally omitted <==**

## **IV. The Information-Theoretic Constants** 

## **9 The natural logarithms:** ln 2 **and** ln 3 

## **The question:** 

Given the natural base _e_ , what is the information content of a distinction on the substrate? 

## **The derivation:** 

The natural logarithm ln _x_ is the inverse of the exponential _e[x]_ . Having derived _e_ , this inverse is forced. 

The most primitive distinction the substrate supports is binary: ground versus not-ground, 0 versus _±_ 1. The information content of this distinction, measured in natural units, is: 

**==> picture [99 x 9] intentionally omitted <==**

The full state space _{−_ 1 _,_ 0 _,_ +1 _}_ is a ternary alphabet. The information content of a single ternary choice is: 

**==> picture [99 x 8] intentionally omitted <==**

This is the information capacity of one symbol of the substrate. It is not assigned; it is measured, using the exponential base the substrate itself produced. 

## **Derived constants:** 

ln 10 follows by the product rule. Since 10 = 2 _×_ 5: 

**==> picture [165 x 9] intentionally omitted <==**

ln 2 = 0 _._ 69314718 _. . ._ ln 3 = 1 _._ 09861228 _. . ._ 

## **V. The Summation Constants** 

## **10** _ζ_ (2) **: the Basel sum** 

## **The question:** 

What is the sum of inverse squares over the positive integers? 

## **The derivation:** 

The integers Z contain the positive integers 1 _,_ 2 _,_ 3 _, . . ._ by repeated composition of the unit step. The sum 

**==> picture [66 x 29] intentionally omitted <==**

is the simplest convergent series formed from inverse powers of the integers’ own counting sequence. 

Its value was first computed by Euler: 

**==> picture [48 x 26] intentionally omitted <==**

_π_ was derived in Section 7. The sum of inverse squares over the integers therefore returns _π_ , squared and scaled. The substrate, summing over its own structure, rediscovers a constant it had already produced by a different route. 

**==> picture [130 x 25] intentionally omitted <==**

## **11** _ζ_ (3) **: Apéry’s constant** 

## **The question:** 

What appears once summation over the positive integers is extended from inverse squares to inverse cubes? 

## **The derivation:** 

By repeated composition of the unit step, the substrate supports the counting sequence 1 _,_ 2 _,_ 3 _, . . ._ . By itself, this does not yet compel a global sum over all inverse cubes. To reach that regime, an additional analytical completion must be admitted: the integer sequence is now treated as the domain of an infinite summation operator. 

Under that demand, 

**==> picture [66 x 29] intentionally omitted <==**

Unlike _ζ_ (2), this sum has no known closed form in terms of _π_ or any other previously derived constant. Apéry proved in 1978 that _ζ_ (3) is irrational. 

The point is not that raw ternary syntax is already evaluating global series in the dark. The point is that, once summation over the integer sequence is admitted as a completion demand, the inverse-cube series yields a constant that appears algebraically independent of the preceding ones and resists reduction to the earlier ladder. 

## **The result:** 

_ζ_ (3) is the constant exposed when the already available counting sequence is carried through the stronger analytical completion of inverse- cube summation. 

**==> picture [102 x 12] intentionally omitted <==**

## **12 The Euler–Mascheroni constant** _γ_ 

## **The question:** 

What is the stable gap between discrete summation and continuous accumulation? 

## **The derivation:** 

The unit step generates the counting sequence 1 _,_ 2 _,_ 3 _, . . ._ and therefore the harmonic partial sums 

**==> picture [55 x 30] intentionally omitted <==**

Having derived the natural logarithm, we can compare this discrete sum to the continuous accumulation of 1 _/x_ : 

**==> picture [65 x 24] intentionally omitted <==**

The difference 

**==> picture [47 x 11] intentionally omitted <==**

converges as _n →∞_ to a constant. This limiting gap is the Euler–Mascheroni constant: 

**==> picture [100 x 16] intentionally omitted <==**

Equivalently, 

**==> picture [111 x 26] intentionally omitted <==**

which makes explicit that _γ_ measures the residue between discrete counting and its smooth logarithmic approximation. 

## **The result:** 

_γ_ is the constant error term forced by comparing the integers’ most primitive divergent sum to the logarithm it asymptotically shadows. It is the simplest measure of how discrete accumulation departs from its continuous limit. 

**==> picture [89 x 11] intentionally omitted <==**

## **13 Catalan’s constant** _G_ 

**The question:** 

What happens when the substrate alternates sign over its own odd inverse squares? 

## **The derivation:** 

The balanced-ternary substrate has sign as an intrinsic feature. The simplest alternating sum over the odd inverse squares is: 

**==> picture [219 x 29] intentionally omitted <==**

This is Catalan’s constant. Like _ζ_ (3), it has no known closed form in terms of elementary constants, and its irrationality remains unproven. It arises naturally in analysis (for example as the Dirichlet beta value _β_ (2)), and in a variety of integrals and integer-grid model evaluations. 

The substrate, exercising its intrinsic sign structure over its own counting sequence, produces a constant that remains opaque to further simplification. 

**==> picture [91 x 9] intentionally omitted <==**

## **14 The lemniscate constant** _ϖ_ 

## **The question:** 

What constant appears once arc-length measurement is extended beyond the circular regime to a simple self-crossing algebraic curve? 

## **The derivation:** 

The lemniscate of Bernoulli, defined in polar coordinates by _r_[2] = cos 2 _θ_ , is the simplest algebraic curve that closes on itself with a crossing at the origin. By itself, the previously established ladder does not yet compel elliptic arc-length measurement. To reach that regime, an additional analytical completion must be admitted: the length of a non-circular smooth curve is now treated as a legitimate global invariant. 

Under that demand, the total arc length of the lemniscate is 

**==> picture [37 x 8] intentionally omitted <==**

where _ϖ_ (the lemniscate constant) is given by 

**==> picture [86 x 27] intentionally omitted <==**

This is a complete elliptic integral. The point is not that raw ternary syntax is already measuring arc lengths of exotic curves. The point is that, once arc-length comparison is extended beyond the circle, the next natural class of invariants is elliptic rather than circular, and the corresponding constant is no longer _π_ but _ϖ_ . 

The two constants are related by 

**==> picture [62 x 27] intentionally omitted <==**

where Γ is the gamma function, itself the unique smooth extension of the factorial to the reals. 

## **The result:** 

_ϖ_ is the constant exposed when arc-length measurement is carried from the circular case into the stronger analytical completion of elliptic geometry. 

**==> picture [91 x 8] intentionally omitted <==**

## **15 Summary of derived constants** 

The following constants have been derived, in order, from the substrate _{−_ 1 _,_ 0 _,_ +1 _}_ and the successive structural or analytical demands admitted in this paper. 

|**Constant**|**Constant**|**Value**|**Appears under**|
|---|---|---|---|
|_i_||_√_<br>_−_1|Quarter-turn between independent axes|
|_√_|2|1_._41421_. . ._|Quadratic comparison on the unit square|
|_√_|3|1_._73205_. . ._|Quadratic comparison on the unit cube|
|_√_|5|2_._23606_. . ._|First non-trivial integer-coordinate distance|
|_φ_||1_._61803_. . ._|A chosen non-trivial integer recurrence|
|_e_||2_._71828_. . ._|Arbitrary refnement with multiplicative compounding|
|_π_||3_._14159_. . ._|Rotational completion of the complex exponential|
|ln 2||0_._69314_. . ._|Binary distinction measured in the base _e_|
|ln 3||1_._09861_. . ._|Ternary distinction measured in the base _e_|
|_ζ_(2)||_π_2_/_6|Inverse-square summation over the integers|
|_ζ_(3)||1_._20205_. . ._|Inverse-cube summation over the integers|
|_γ_||0_._57721_. . ._|Harmonic–logarithm comparison|
|_G_||0_._91596_. . ._|Alternating inverse-square summation|
|_ϖ_||2_._62205_. . ._|Elliptic arc-length completion|



Every entry in this table appears only once the available inventory is carried through an additional explicit demand. In the earlier sections, those demands were structural: independence, quadratic comparison, symmetry-preserving operators. In the later sections, they were analytical: recurrence, refinement, rotation, summation, and arc-length comparison. 

The table is not claimed to be exhaustive. It is claimed to be _ordered_ : each constant depends only on structure or completion machinery already on the page, and no constant could have appeared earlier in the ladder than the stage at which it is introduced. 

## **16 Discussion** 

## **Scope:** 

This paper derives a sequence of mathematical constants from the structural operations available to the balanced-ternary state space, but it now makes an explicit distinction between primitive substrate content and later analytical completion demands. Some constants follow once additional structural commitments such as independent generators, quadratic comparison and symmetry-preserving operators are admitted. Others appear only when the substrate is examined through stronger completion principles such as recurrence, refinement, rotation and summation. 

The claim is therefore ordered rather than absolute. The paper does not claim that every later constant is already present in raw ternary syntax. It claims that, once each additional demand is stated openly, the resulting constants enter in a strict derivation ladder and do so at the earliest stage permitted by the available machinery. No physical interpretation is assumed or required. 

## **What is new:** 

The individual constants are, obviously, not new. What is new is the sequential derivation from a single starting point, together with a clear bookkeeping of ontological status. The sequence is not presented as a flat list of consequences all carrying the same force. It is presented as an ordered map from a minimal discrete substrate to the hierarchy of constants revealed when increasingly strong completion demands are imposed. 

## **What is not claimed:** 

The paper does not claim that all mathematically significant constants can be derived in this way. It does not claim that the derivation chain is the unique such chain. It does not claim that the balanced-ternary substrate, in isolation, is spontaneously “doing calculus” or evaluating global sums without further analytical structure being admitted. 

What it does claim is narrower and stronger: given the stated succession of structural and analytical demands, _this particular ladder_ is ordered, coherent, and non-arbitrary. Each link follows from machinery already on the page, and the starting point was itself established as a logical necessity in the companion paper. 

## **Open question:** 

Whether the constants derived here, taken together, suffice to reconstruct a broader mathematical framework beyond the starting alphabet remains open. The present paper does not resolve that question. It establishes only the ladder itself, the order in which its constants appear, and the completion demands under which they do so. 

## **17 Conclusion** 

The balanced-ternary state space _{−_ 1 _,_ 0 _,_ +1 _}_ is not inert. Once it is subjected to successive structural and analytical completion demands, it exposes a determinate ladder of constants whose order is not arbitrary. Some arise from comparatively primitive extensions of the substrate, such as independent generators, quadratic comparison and symmetry-preserving operators. Others appear only under stronger analytical completions, including recurrence, refinement, rotation and summation. 

The sequence begins with the structure of independent axes and proceeds, in order, through the fundamental irrationals, self-referential growth constants, rotation-based invariants, information-theoretic logarithms, and the simplest convergent integer sums. The paper does not claim that all of these are primitive contents of raw ternary syntax. It claims that, once each added demand is made explicit, the resulting constants enter in a strict sequence at the earliest stage permitted by the available machinery. 

No numerical value was tuned. Where a choice of scale is required, it is fixed by an explicit normalisation. No constant is inserted ad hoc. The claim is therefore not that the substrate contains the whole edifice in finished form, but that it supports a disciplined, non-arbitrary derivation ladder whose constants appear in order under its admissible completions. 

