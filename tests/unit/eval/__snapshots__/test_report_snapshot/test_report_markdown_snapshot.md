# Evaluation report

- Generated: 2026-10-08 12:00:05 UTC
- Split: dev
- Matching: strict (categories must be compatible)
- Cases: 3 (clean 1, defect 1, design 1)
- Producer: engine fixture-1, model none
- Evaluation key version: 1

Precision is (matched + adjudicated valid) / n. While adjudications are pending it is shown as [pending counted wrong, pending counted right].

## Inline precision

| Category | Precision | Correct | Pending | Invalid | Duplicate |
|---|---|---|---|---|---|
| all | [42.9%, 57.1%] (n=7, 1 pending) | 3 | 1 | 2 | 1 |
| lint | [0.0%, 100.0%] (n=1, 1 pending) | 0 | 1 | 0 | 0 |
| maintainability | 100.0% (n=1) | 1 | 0 | 0 | 0 |
| correctness | 66.7% (n=3) | 2 | 0 | 0 | 1 |
| reliability | 0.0% (n=1) | 0 | 0 | 1 | 0 |
| performance | 0.0% (n=1) | 0 | 0 | 1 | 0 |

## Summary precision

| Category | Precision | Correct | Pending | Invalid | Duplicate |
|---|---|---|---|---|---|
| all | 66.7% (n=3) | 2 | 0 | 1 | 0 |
| design | 50.0% (n=2) | 1 | 0 | 1 | 0 |
| security | 100.0% (n=1) | 1 | 0 | 0 | 0 |

## High-severity recall

| Channels | Recall | Matched | Labels |
|---|---|---|---|
| inline + summary | 66.7% | 2 | 3 |
| inline only | 33.3% | 1 | 3 |

## False positives per PR

[0.67, 1.00] (2 invalid inline, 1 pending, 3 cases)

## Inline comments per case

Mean 2.33, max 3.

## Per-rule precision (design, maintainability)

| Rule | Precision | Correct | Pending | Invalid | Duplicate |
|---|---|---|---|---|---|
| C901 | 100.0% (n=1) | 1 | 0 | 0 | 0 |
| layering.api-db | 50.0% (n=2) | 1 | 0 | 1 | 0 |

## Missed must-find labels

- case-defect / L3

## Cases over expect.max_inline

- case-defect: 3 inline comments (limit 2)

## Not scored

- annotation: 1 finding

## Pending adjudications (1)

| Case | Channel | Category | Location | Title | Key |
|---|---|---|---|---|---|
| case-defect | inline | lint | src/a.py:1 | Finding P4 | 03587a22c945 |

Run `aireview-eval adjudicate` to decide them.
