# BTCU Token Economy Report

## Simulation Parameters

- Total inputs: 1000
- Stage split: 20% school / 40% internalize / 40% graduate
- Snapshot interval: every 50 steps

## Results

- Final LLM calls: 400
- Final patterns learned: 200
- Final reuse rate: 80.0%
- Final unique states: 200

## Key Finding

As the agent progresses from school to graduate stage,
pattern learning reduces LLM dependency.
In a production system with real LLM, the savings would be:

```
school:     C ~ N        (every input needs LLM)
internalize: C ~ N * (1 - r)  (r = reuse_rate)
graduate:    C ~ N * u      (u = unknown_rate → 0)
```
