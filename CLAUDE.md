# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Milestones 1 and 2 are done: a single-repo report reconciled with `tkus rollup`, finished 16:9
slides (`tkus-vis slides`), and the PR join (`--repo OWNER/NAME`), which adds cost per merged PR,
the most expensive PRs, spend against merged PRs, and coverage.
The design brief `tkus-vis-init.md` is the spec. Read the relevant section before substantive
changes.

**Current priority:** high-quality slide infographics, which are pasted into a deck by hand.
Milestone 3 (organisation scope: many repos, team mapping) comes next. Phone, responsive and
cross-OS support are out of scope; slide export needs macOS with Google Chrome. Decided: charting
(Vega-Lite via vl-convert), GitHub auth (`GITHUB_TOKEN`, else `gh auth token`), `--repo`. Still
open (brief §9): `--org` shape, team mapping, hosting, org auth. natekot/tkus has no merged PRs
yet, so its deck honestly shows none; the joined deck is designed against `tests/demo_data.py`.

## Repository

Public at github.com/natekot/tkus-vis, MIT licensed. Rulesets guard `main`. Changes arrive by pull
request, with CI (`.github/workflows/ci.yml`) passing and a code-owner review (`.github/CODEOWNERS`
lists @natekot and @nate-kot). Only @natekot, as admin, bypasses that. Nobody can force-push or
delete `main`, and only @natekot can push `v*` tags.

Releases are semver tags. Move `CHANGELOG.md`'s Unreleased notes under the new version, then run
`/ship`, which bumps `[project].version`, tags `vX.Y.Z` and pushes. The tag runs
`.github/workflows/release.yml`, which reruns CI, checks the tag against the version, and
publishes a GitHub Release with the wheel, the sdist and that version's changelog section.
CI runs on macOS, so the Chrome export tests run. It checks out natekot/tkus at a pinned tag
as the reconciliation oracle, and that pin is bumped deliberately.

## Commands

```sh
uv sync                                         # create .venv with dev tools
uv run pytest                                   # all tests
uv run pytest tests/test_model.py::test_real_tkus_ledger_is_pinned   # one test
uv run ruff format && uv run ruff check         # before every commit
uv run tkus-vis build --path ../tkus -o out/tkus.html   # a real report (out/ is ignored)
uv run tkus-vis slides --path ../tkus -o out/slides   # slide PNGs + one PDF (needs Google Chrome)
uv run tkus-vis slides --repo natekot/tkus -o out/slides  # ledger + PRs through GitHub (read-only)
uv run python tests/record_github.py natekot/tkus tests/fixtures/github/natekot-tkus   # re-record
```

`tests/test_reconcile.py` runs tkus from source as an oracle. It finds tkus at `$TKUS_SRC`,
defaulting to `../tkus`, and is skipped when tkus is missing.

## Code map

`collect.py` (the only module that runs git) → `ledger.py` (format: path rules, parsing,
`Snapshot`) → `model.py` (pure; per-currency views, buckets, audit rows without identities)
→ `render.py` + `templates/report.html.j2` (formatting only) ← `cli.py` wires them together.
Slides branch off the model: `story.py` (pure: each slide's numbers and takeaway sentence, pinned
by tests) → `charts.py` (Vega-Lite specs rendered to SVG by vl-convert; the look lives in
`theme.py`) → `export.py` + `templates/slide.html.j2` (1920×1080 HTML, printed to 2x PNGs and
one vector PDF by Chrome via Playwright, flagging slides that overflow). With `--repo`, `github.py`
reads the ledger and PRs through read-only REST calls behind an injectable `fetch` (tests use
`helpers.fake_github` and `helpers.replay`, never the network), and `model._match`/`_coverage`
apply the spec §4 join: sanitised head refs, earliest PR still open when the usage ended, forks
unmatched, buckets PR/direct/unmatched. Before changing a chart,
load the `dataviz` skill, and look at the rendered PNGs before calling it done.
Tests build real git repos through `tests/helpers.py` and `tests/conftest.py`, with git config
isolated from the user's. `tests/fixtures/tkus-ledger/` is the real ledger pinned at tkus@b6fce91.

## What it is

An executive report of AI agent spend joined with delivery output: cost per
merged PR, spend against PR throughput, the most expensive PRs, and breakdowns by
team, repo, model and provider. The readers are directors, not developers. It
works at single-repo or org scope through one pipeline, since a repo is an org of
one.

## Boundary with tkus

[tkus](https://github.com/natekot/tkus) is the collector. Its git hooks write a
priced ledger to `.tkus/<identity>/<branch>.jsonl` in each repo. tkus-vis only
reads that ledger.

- **The latest tkus is checked out at `../tkus`** (0.11.0, tracking `origin/main`).
  The spec is the "Ledger format" section of `../tkus/README.md`.
- **Never import tkus or depend on its internals.** Depend only on the documented
  file format. tkus-vis must work through the GitHub API on repos where tkus was
  never installed.
- tkus-vis is read-only toward the repos it analyses. It writes nothing to them
  and opens no PRs or issues.
- You may read tkus source to match its behaviour. These are the reference points:
  - **Name sanitisation** is in `_sanitize` and `_branch_path` in
    `../tkus/tkus/repoledger.py`. It runs on **each `/`-separated segment** of a
    branch name: trim whitespace, replace `[<>:"\\|?*\x00-\x1f]` with `-`, then
    strip leading and trailing dots and spaces. A segment left empty becomes `-`,
    and a name left empty becomes `detached`. Identities have `/` replaced by `-`
    and fall back to `unknown`. PR head refs must go through the same function
    before they are matched to ledger paths.
  - **Path → (identity, branch)** is in `_ledger_scope` in `../tkus/tkus/__main__.py`.
    The first segment after `.tkus/` is the identity. Everything after it, minus
    `.jsonl`, is the branch.
  - **Entry → commit** is in `_introduced_by` and `_commit_index` in the same file.
    tkus runs `git log --first-parent -m -p --no-renames -- .tkus`, and the oldest
    commit whose diff adds the line wins. When no commit added the line, it falls
    back to the commit whose first parent is the entry's `parent` (`null` means
    the root commit). An entry is identified by `(until or at, since, parent)`
    (`entry_key` in `repoledger.py`), which excludes the priced fields.

## tkus as a test oracle

`tkus` is not on PATH. Run it from source inside the clone you are checking:

```sh
TKUS=$(cd ../tkus && pwd)          # run from the tkus-vis root
cd <clone> && PYTHONPATH=$TKUS python3 -m tkus rollup --json [--by branch|identity|date]
cd <clone> && PYTHONPATH=$TKUS python3 -m tkus log --json --branch NAME
```

Gotchas for reconciliation tests:
- `rollup` reads the **working-tree contents of tracked** `.tkus/` files. It does
  not read `HEAD`. Reconcile only against a clean checkout of the ref.
- `--by branch` merges identities, so `main` sums `natekot/main.jsonl` and
  `nate-kot/main.jsonl`. `--by date` keys on the first 10 characters of `until`
  (falling back to `at`).
- `total` is an unrounded float sum, for example `66.90734339999999`. Compare it
  with a tolerance.
- `log --branch X` walks X's own first-parent history. For a branch that was
  squash-merged and deleted, it reports `commits: []` with every entry under
  `orphaned`. Use it as an oracle on the default branch, not on merged feature
  branches.
- tkus's `rollup` (0.10.0 and 0.11.0) skips non-ASCII ledger paths (`git ls-files` without `-z`).
  tkus-vis reads them. `test_non_ascii_paths_reconcile` is a strict xfail that flips
  when tkus fixes it.

## Sample data

- The real ledger is `../tkus/.tkus/`. It has two identities, `natekot` and
  `nate-kot`, which are the same person (see `../tkus/.github/CODEOWNERS`). That
  makes it a real case for identity → person mapping.
  `nate-kot/fix-amend-rename-attribution.jsonl` holds a `since: null` backlog
  entry.
- `../tkus/tests/fixtures/real_sample.jsonl` is a Claude Code **transcript**
  fixture, not a ledger. Do not use it as ledger input.
- tkus's own test suite uses stdlib unittest: `python3 -m unittest discover -s tests -t .`.

## Python on this machine

`uv` manages the interpreter (`.python-version` pins 3.12, and the floor is 3.10). The
system `python3` is 3.9 and is only good for running tkus itself.

## Planned architecture (brief §8)

There are four stages with plain data passed between them, so each stage can be
tested alone:

```
collect -> enrich -> model -> render
```

- **collect** reads `.tkus/**/*.jsonl` from the default branch's **current tree
  only**. Never sum across history: a rename moves entries between files, so
  summing history double-counts them. Through the GitHub API, fetch only the
  `.tkus/` subtree, because recursive-tree listings truncate on large repos.
  Locally, use `git ls-tree` and `git show`. Skip a corrupt line with a warning;
  it is never fatal. Ignore unknown fields, and read a missing counter as 0.
- **enrich** lists PRs once per repo and indexes them by sanitised `headRefName`.
  It also fetches team membership and caches API responses on disk. Keep the git
  host behind a small interface: GitHub first, then possibly GHE or GitLab.
- **model** is pure functions with no I/O. It applies the join and bucket rules,
  and most tests live here.
- **render** turns the dataset into self-contained HTML: inline CSS, JS and data,
  no CDN at view time, readable in light and dark, printable to PDF. It also
  writes the joined dataset (JSON or CSV) alongside. It does no calculation
  beyond formatting.

### Join rules (brief §4)

- A ledger branch path matches a sanitised PR head ref. Sum every identity's file
  for the same branch.
- When a branch name was reused across PRs, assign each entry to the earliest PR
  whose `merged_at` (or `closed_at`) is at or after the entry's `until`.
- Every dollar lands in exactly one bucket:
  - **PR-attributed**
  - **Direct to default branch**, from `<default>.jsonl`
  - **Unmatched branch**: renames tkus didn't see, deleted branches, fork PRs, and `detached`
- PR cost is the branch's **own** spend. Work merged in from another branch stays
  attributed to the branch it was written on.
- Identities map to people and teams through a config file first, then the PR
  author, then GitHub Teams or CODEOWNERS. Show unmapped identities as unmapped,
  and never guess.

## Accuracy rules (non-negotiable, brief §5)

1. Use each entry's recorded `usd`. Never re-price.
2. Label the money as list price (or the configured override). For subscription
   users it is notional, so say that in the methodology note.
3. Missing data is a coverage gap, not zero cost. This covers repos with no
   ledger, `--local-only` repos, `--no-verify` commits and pre-install work.
4. Coverage goes on the front page: repos scanned vs. repos with a ledger, and
   merged PRs vs. merged PRs with cost data.
5. Totals reconcile: the three buckets sum to the tree total, which equals
   `tkus rollup --json`'s `total`. Enforce this with an automated test.
6. A `since: null` entry is install backlog. Keep it in totals, exclude it from
   per-PR distributions by default, and mark it.
7. Never sum across currencies. Group by `currency`, and warn when more than one
   appears.
8. There are two clocks. Spend over time buckets by `until`. Cost per merged PR
   uses `merged_at` and the PR's whole cost.
9. Lead with the median cost per PR and show the spread. Never show a mean alone.

## Privacy (brief §6)

- Default views aggregate by team, repo and org. Per-person breakdowns are opt-in
  through config.
- Never emit email addresses. Ledger identities are git display names, never
  emails.
- Don't enrich with commit diffs or PR bodies. Use PR titles and links only.

## Testing (brief §11)

- Unit tests never touch the live network. The API layer is tested against
  recorded responses.
- Required invariants:
  - bucket totals equal the tree total
  - summing per-PR costs double-counts nothing
  - per-period totals sum to the overall total
- Edge-case fixtures:
  - reused branch names
  - forbidden characters in branch names
  - renamed branches, both folded and unfolded
  - `since: null` entries
  - several identities on one branch
  - corrupt lines and unknown fields
  - mixed currencies
  - a repo with no ledger
- Render tests: a snapshot of the HTML structure, plus a check that the page
  loads with no network access.

## Milestones (brief §10)

1. Local single repo, no network: read the ledger from a clone, bucket by branch,
   render minimal HTML, and pass reconciliation against `tkus rollup --json`.
2. PR join: GitHub enrichment, the three buckets, cost per merged PR, top PRs and
   coverage.
3. Org scope: many repos, team mapping, and team and repo breakdowns.
4. Scheduled publishing: a CI workflow, API caching, and period-over-period
   comparison.
