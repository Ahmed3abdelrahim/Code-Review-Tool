# Benchmark

Offline benchmark for the reviewer (plan section 8, decisions D20 and D21). Every case is a
pull request frozen as a two-commit snapshot bundle, with hand-written labels.

## Layout: one root per split

Dev material lives under `eval/`; **all holdout material lives under `eval/holdout/`**, with
the same structure. Every `aireview-eval` command except `validate` works on one split and
takes its paths from that split's root: `--split dev` (default) uses `eval/`,
`--split holdout` uses `eval/holdout/`.

```
eval/                                  # dev root
├── cases/<case>.yaml                  # one case: source, bundle SHAs, labels (split: dev)
├── seeds/<repo>/<case>/               # planted-bug cases: base/ and head/ trees, optional pr.md
├── bundles/<case>.bundle              # two snapshot commits per case (≤ 5 MB, ≤ 100 MB in total)
├── policies/<repo>.yml                # .ai-review.yml of each repository (default.yml: defaults)
├── baselines/coderabbit/<case>.json   # exported CodeRabbit review comments
├── baselines/coderabbit_overrides.yaml   # optional category/severity corrections
├── baselines/coderabbit_predictions.json # converted predictions
├── baselines/coderabbit.json          # baseline summary (Phase 0 gate)
├── adjudications.jsonl                # verdicts on unmatched predictions (append-only)
├── reports/                           # aireview-eval score output
├── repos/                             # local clones and sandbox clones (git-ignored)
└── holdout/                           # holdout root: same structure (cases with split: holdout)
```

`aireview-eval validate` checks both roots: case ids are unique and splits are
repository-disjoint across them, a case under `eval/cases/` must have `split: dev` and a case
under `eval/holdout/cases/` must have `split: holdout`. Bundles and policies are relative to
their case's root.

## Holdout isolation

Holdout material is off-limits to Claude (Claude Code): a deny rule
(`Read(eval/holdout/**)`) and the PreToolUse hook (any Bash command mentioning
`eval/holdout` is blocked) enforce it. Only the harness, run by the maintainer, reads it.
**Holdout seed-build, adjudication, scoring and reports are run by the maintainer only, who
shares only aggregate metrics with Claude.** Holdout runs happen at phase gates and are
logged in DECISIONS.md.

Output Claude reads never quotes holdout material (D22): `aireview-eval validate
--redact-holdout` and every `--split dev` command reduce errors involving holdout cases to a
count and case ids, and the benchmark integrity tests report holdout problems the same way.
Run plain `aireview-eval validate` yourself to see the details.

## Planted-bug cases (seeds)

1. Write the two snapshots: `<root>/seeds/<repo>/<case>/base/` and `.../head/`. Optionally
   add `.../pr.md` (first line: PR title; the rest: description). Neither the code, comments,
   file names nor `pr.md` may hint at the planted bug.
2. Build the bundles (git runs only in temporary directories; nothing is pushed):
   `aireview-eval seed-build [--split holdout] [--case <id>]`. It prints the bundle SHAs and
   checks them against `<root>/cases/<case>.yaml`.
3. Write `<root>/cases/<case>.yaml` with `provenance: planted`, the printed
   `bundle_base_sha` and `bundle_head_sha`, and the labels. `source.base_sha`/`head_sha` are
   omitted for planted cases. Use the same `source.repo` for all cases of one seed repository.
4. `aireview-eval validate` (Claude runs it with `--redact-holdout`).

Every case of a seed repository uses that repository's policy, `policies/<repo>.yml`, and both
the `base/` and `head/` trees contain a byte-identical copy as `.ai-review.yml`, so sandbox
runs see the same configuration (D22; checked by `test_seed_policy_matches_case_policy`, for
holdout seeds too). `test_seed_bundles_match_seed_trees` fails when a seed changed without
re-running `seed-build`.

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

## CodeRabbit baseline (per split)

1. `aireview-eval sandbox-commands --org <sandbox-org> [--split holdout]` prints, per case,
   the commands that push the snapshot commits as branches to `<sandbox-org>/<repo>`, open
   the pull request and later export CodeRabbit's comments into
   `<root>/baselines/coderabbit/`. You run them; nothing is executed by the tool.
2. After CodeRabbit has reviewed every PR, run the printed `gh api --paginate …` commands.
3. `aireview-eval import-coderabbit [--split holdout]` converts the top-level inline
   comments of `coderabbitai[bot]` into `<root>/baselines/coderabbit_predictions.json`.
   Category and severity come from CodeRabbit's markers; correct them in
   `<root>/baselines/coderabbit_overrides.yaml`:

   ```yaml
   - id: 123456789        # the comment id from the export
     category: security
     severity: high
   ```
4. `aireview-eval adjudicate --matching location --predictions eval/baselines/coderabbit_predictions.json`
   (code is shown from the bundles; add `--split holdout` and the holdout predictions path
   for the holdout).
5. `aireview-eval score --matching location --predictions eval/baselines/coderabbit_predictions.json --summary-out eval/baselines/coderabbit.json`
   (likewise with `--split holdout` for the holdout).

External baselines use `--matching location` (categories ignored), because their
categories are mapped heuristically. Our engine is scored with strict matching; for the
comparison table it is also scored once with `--matching location`. Every report states
its matching mode.
