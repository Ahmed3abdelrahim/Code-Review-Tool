# Benchmark

Offline benchmark for the reviewer (plan section 8, decisions D20 and D21). Every case is a
pull request frozen as a two-commit snapshot bundle, with hand-written labels.

```
eval/
├── cases/<case>.yaml              # one case: source, bundle SHAs, labels (validated)
├── seeds/<repo>/<case>/           # planted-bug cases: base/ and head/ trees, optional pr.md
├── bundles/<case>.bundle          # two snapshot commits per case (≤ 5 MB, ≤ 100 MB in total)
├── policies/default.yml           # .ai-review.yml used by the cases
├── baselines/coderabbit/<case>.json      # exported CodeRabbit review comments
├── baselines/coderabbit_overrides.yaml   # optional category/severity corrections
├── baselines/coderabbit_predictions.json # converted predictions
├── baselines/coderabbit.json             # baseline summary (Phase 0 gate)
├── adjudications.jsonl            # verdicts on unmatched predictions (append-only)
├── reports/                       # aireview-eval score output
└── repos/                         # local clones (git-ignored)
```

## Planted-bug cases (seeds)

1. Write the two snapshots: `seeds/<repo>/<case>/base/` and `seeds/<repo>/<case>/head/`.
   Optionally add `seeds/<repo>/<case>/pr.md` (first line: PR title; the rest: description).
   Neither the code, comments, file names nor `pr.md` may hint at the planted bug.
2. Build the bundles (git runs only in temporary directories; nothing is pushed):
   `aireview-eval seed-build` (or `--case <id>` for one case). It prints the bundle SHAs
   and checks them against `cases/<case>.yaml`.
3. Write `cases/<case>.yaml` with `provenance: planted`, the printed `bundle_base_sha` and
   `bundle_head_sha`, and the labels. `source.base_sha`/`head_sha` are omitted for planted
   cases. Use the same `source.repo` for all cases of one seed repository.
4. `aireview-eval validate`.

Seed trees must contain exactly what git records here: no symlinks, no `.git`, and nothing
this repository's `.gitignore` ignores (for example `.env`, `build/`, `dist/`,
`node_modules/`, `*.pem`). Fake secrets belong in `.py` or `.txt` files.

## Open-source cases (real bugs)

1. Clone the repository under `eval/repos/<name>` (a plain `git clone`).
2. Snapshot the two upstream commits (reads the clone, never modifies it):
   `aireview-eval snapshot-upstream --repo-dir eval/repos/<name> --case <id> --base <sha> --head <sha> --title "<PR title>"`
3. Write `cases/<id>.yaml` with the upstream `source.base_sha`/`head_sha` (provenance), the
   printed bundle SHAs, the license (MIT, Apache-2.0, BSD-2/3-Clause, ISC, 0BSD, Zlib,
   PSF-2.0, Unlicense, CC0-1.0, or `own`) and the labels.

Splits are repository-disjoint: a repository's cases are all `dev` or all `holdout`.

## CodeRabbit baseline

1. `aireview-eval sandbox-commands --org <sandbox-org>` prints, per case, the commands that
   push the snapshot commits as branches to `<sandbox-org>/<repo>`, open the pull request and
   later export CodeRabbit's comments. You run them; nothing is executed by the tool.
2. After CodeRabbit has reviewed every PR, run the printed `gh api --paginate …` commands
   (one file per case in `baselines/coderabbit/`).
3. `aireview-eval import-coderabbit` converts the top-level inline comments of
   `coderabbitai[bot]` into `baselines/coderabbit_predictions.json`. Category and severity
   come from CodeRabbit's markers; correct them in `baselines/coderabbit_overrides.yaml`:

   ```yaml
   - id: 123456789        # the comment id from the export
     category: security
     severity: high
   ```
4. `aireview-eval adjudicate --split all --matching location --predictions eval/baselines/coderabbit_predictions.json`
   (code is shown from the bundles).
5. `aireview-eval score --split all --matching location --predictions eval/baselines/coderabbit_predictions.json --summary-out eval/baselines/coderabbit.json`

External baselines use `--matching location` (categories ignored), because their
categories are mapped heuristically. Our engine is scored with strict matching; for the
comparison table it is also scored once with `--matching location`. Every report states
its matching mode.
