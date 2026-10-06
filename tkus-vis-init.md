# tkus-vis — design brief

> **For the agent reading this:** this is the founding brief for a new
> repository, `tkus-vis`. It describes what the tool is for, the data it
> consumes, the rules it must follow to stay accurate, and a suggested build
> order. Use it to write the repository's `CLAUDE.md` and to scaffold
> milestone 1. Anything under **Open decisions** belongs to the user. Confirm
> those before building past milestone 1.

---

## 1. What this is

`tkus-vis` produces an **executive view of AI agent spend joined with delivery
output**: what AI-assisted engineering cost, and what it shipped. It is for
directors and executives, not developers. A reader should understand the
headline numbers in under a minute, with nobody there to explain them.

It works at two scopes with one pipeline:

- **Single repository**: for a project review.
- **Organisation**: many repositories, grouped by team. A single repo is just
  an org of one.

### Relationship to tkus

[`tkus`](https://github.com/natekot/tkus) is the **collector**. Git hooks on
each developer's machine read the usage records that Claude Code and GitHub
Copilot CLI already write locally. The hooks price that usage and commit it to a
ledger inside the repository, at `.tkus/<identity>/<branch>.jsonl`.

`tkus-vis` is a **consumer** of that ledger. The boundary is deliberate:

| | tkus | tkus-vis |
|---|---|---|
| Runs | On every commit, on developer machines | On demand or on a schedule (CI) |
| Network | **Never** | Yes: GitHub API |
| Dependencies | **None** (the hook must not break) | Whatever serves the job |
| Audience | Developers | Directors, executives |
| Writes to repos | Its own ledger file | **Nothing**: read-only |

`tkus-vis` depends **only on the documented ledger file format**, never on tkus
internals or imports. It must work against repositories where it was never
installed. The canonical format spec is the "Ledger format" section of the tkus
README, published in tkus 0.10.0 and summarised in section 3.

---

## 2. Goals and non-goals

**Goals**
- Show cost **next to output**: cost per merged PR, spend against PR
  throughput over time, and the most expensive features with links.
- Break spend down by team, repository, model and provider.
- Be **auditable**: every figure traces back to ledger entries, and totals
  reconcile with `tkus rollup` (section 5).
- Be **honest about coverage**: what share of repos and PRs carry data at all.
- Produce a **self-contained static HTML report** that works offline, prints
  cleanly to PDF, and can be emailed or hosted anywhere.

**Non-goals**
- Collecting usage. That is tkus's job.
- Re-pricing. Use the `usd` recorded in each entry (section 5).
- Writing to analysed repositories, or opening PRs or issues on them.
- Real-time dashboards. A periodic snapshot is enough.
- Per-developer leaderboards **by default** (section 6).

---

## 3. Input: the tkus ledger

### Location

```
.tkus/<identity>/<branch>.jsonl
```

- `<identity>` is the developer's git `tkus.identity`, falling back to
  `user.name`, with `/` replaced by `-`. It is **not** a GitHub login and
  **never** an email address. tkus avoids publishing emails on purpose, and
  tkus-vis must do the same.
- `<branch>` keeps its slashes as nested directories: `feature/x` is stored as
  `.tkus/alice/feature/x.jsonl`. A detached HEAD is filed under `detached`.
- In both names, characters Windows forbids in filenames (`<>:"\|?*` and
  control characters) are replaced with `-`. Leading and trailing dots and
  spaces are stripped.
- One file per identity per branch is what keeps concurrent PRs from causing
  merge conflicts.
- When a branch is renamed, tkus moves its entries, unchanged, into the new
  name's file at the next commit. It sees renames through the local reflog or
  an explicit `tkus rename`. A rename it can't see leaves the entries under the
  old name.
- Read the **current tree** only. Never sum across historical versions of the
  files: a rename moves entries from one file to another, so summing history
  would count them twice.

### Entries

One JSON object per line, one line per commit that had any AI usage:

```json
{"at": "2026-09-08T19:04:26.645Z",
 "since": "2026-09-08T18:55:12.388Z", "until": "2026-09-08T19:04:26.645Z",
 "parent": "5dc98a31357c5e2300982b64c17948bcd3d90e7a",
 "currency": "USD", "usd": 4.721591, "rates_version": "2026-08",
 "providers": [{"provider": "claude-code", "model": "claude-opus-5",
                "reqs": 48, "in": 96, "out": 24875, "cr": 7279392,
                "cw1h": 45954, "usd": 4.721591}]}
```

| Field | Meaning |
|---|---|
| `at` | When the entry was written (UTC, ISO 8601) |
| `since`, `until` | The usage window this entry claims. `since: null` marks the **first entry after install**, which absorbs all earlier usage (possibly weeks of it) |
| `parent` | SHA of `HEAD` when the commit was made; `null` for a root commit. A **fallback only** (see below) |
| `currency`, `usd` | Entry total |
| `rates_version` | Rate-table version that priced it |
| `providers[]` | One row per provider and model: `provider` (`claude-code` or `copilot`), `model`, `usd`, and token counters |

Counters (a counter that is zero is omitted, so read a missing one as 0): `reqs`
requests, `in` uncached input, `out` output, `cr` cache reads, `cw1h`/`cw5m`
cache writes by TTL, `ws` web searches, `reas` reasoning tokens, `naiu` Copilot
nano AI Units.

**Stability contract:** fields may be added but are never renamed or removed.
Ignore unknown fields. An entry's content is never rewritten; a rename moves
it to another file unchanged.

**Which commit an entry belongs to:** the commit whose diff *added* that line
to a ledger file (walk `git log -p` on `.tkus/`). That survives amend and
rebase. Use `parent` only for a line no commit added. This is how `tkus log`
attributes entries, so match it. After a squash merge, every entry from the
branch belongs to the squash commit.

A real, public sample lives in the tkus repository itself: `.tkus/natekot/*.jsonl`
on `main` at github.com/natekot/tkus.

### Optional local inputs

When running against a local clone with tkus installed, these give the same
numbers and serve as a cross-check:

- `tkus rollup --json [--by branch|identity|date]` (tkus 0.10.0 or later) returns
  `{"by", "currency", "total", "groups": [{"name", "entries", "usd"}]}`.
- `tkus log --json --branch NAME` returns
  `{"branch", "currency", "total", "commits": [{"sha", "subject", "at", "usd"}], "orphaned": [...]}`.

Use these as test oracles, not as the primary input. The primary input has to
work through the GitHub API without tkus installed.

---

## 4. Joining cost to output

### Why the ledger survives into the default branch

GitHub's squash+merge drops commit messages but keeps every file change. So
once a feature branch merges, by squash, merge commit or rebase,
`.tkus/<identity>/<branch>.jsonl` is present in the **default branch's tree**.
Reading only the default branch therefore gives the cost of all merged work.
Unmerged work's ledger lives only on its own branch.

### The join key: ledger branch name → PR head ref

1. List the repo's PRs once (REST `pulls?state=all` paginated, or GraphQL) and
   index them by `headRefName`. Do this instead of one lookup per branch.
2. Before comparing, run PR head refs through the **same sanitisation** as the
   ledger path (section 3), or names containing forbidden characters won't match.
3. If one branch name maps to **several PRs** (the name was reused), assign each
   entry to the earliest PR whose `merged_at` (or `closed_at`) is at or after the
   entry's `until`.
4. Sum every identity's file for the same branch. A branch two people worked on
   is one PR.

### Buckets that must not disappear

Every dollar in the tree lands in exactly one bucket:

| Bucket | Source |
|---|---|
| **PR-attributed** | Branch file matched to a PR |
| **Direct to default branch** | `<default>.jsonl`: commits made straight to `main` |
| **Unmatched branch** | No PR found: renames tkus couldn't see (entries left under the old name), deleted branches, fork PRs, `detached` |

PR cost is the branch's **own** spend. Work that arrived through a merge stays
attributed to the branch it was written on, so summing PRs double-counts
nothing. This is the same rule tkus uses.

### People and teams

Ledger identities are git display names. Mapping them to people and teams needs
an explicit source, in this order:
1. A config file (identity → GitHub login → team), the authority when present.
2. Otherwise, the author of the PR the branch matched.
3. Teams from GitHub Teams membership or CODEOWNERS, as configured.

Unmapped identities show up as such. Never guess silently.

---

## 5. Accuracy rules (non-negotiable)

These come from tkus's own design ethos: a wrong number is worse than a missing
one.

1. **Use recorded `usd`; never re-price.** It is the cost tkus computed with
   the rates in force at the time.
2. **Label the money honestly.** The figure is list price, or the repo's
   configured override. For subscription users it is **notional**: what the
   tokens would cost, not what was billed. Say so in the report's methodology
   note.
3. **No data ≠ zero cost.** Repos without a ledger, `--local-only` repos,
   commits made with `--no-verify`, and work before tkus was installed are all
   *unknown*, not free. Report them as coverage gaps.
4. **Show coverage on the front page**: repos scanned vs. repos with a ledger,
   and merged PRs in the period vs. merged PRs with cost data.
5. **Totals reconcile.** For any repo and ref, the sum of all three buckets
   equals the sum of every entry in the tree, which equals `tkus rollup --json`'s
   `total` for a clone at that ref. Make this an automated test.
6. **Flag install backlog.** An entry with `since: null` may hold weeks of
   pre-install usage. Keep it in totals, but exclude it from per-PR
   distributions by default, and mark it.
7. **Never sum across currencies.** Group by `currency`, and warn if more than
   one appears.
8. **Two clocks, stated explicitly.** "Spend over time" buckets entries by
   `until`. "Cost per merged PR" uses the PR's `merged_at` and includes the PR's
   whole cost, whenever it was incurred.
9. **Skewed distributions:** lead with the median cost per PR and show the
   spread. A mean alone misleads.

---

## 6. Privacy

The ledger already publishes per-developer spend to anyone with repo access.
`tkus-vis` should not amplify that:

- Default views aggregate by **team, repo and org**. Per-person breakdowns are
  opt-in by configuration.
- Never emit email addresses.
- Ledgers contain no prompt or response text. Keep it that way: don't enrich
  with commit diffs or PR bodies beyond titles and links.

---

## 7. The executive view

A single page, read top to bottom:

1. **Headline tiles**: total spend in the period, merged PRs with AI usage,
   median cost per merged PR, and change against the previous period.
2. **Spend vs. throughput**: weekly spend alongside merged-PR count.
3. **Cost per PR distribution**: a histogram or box plot, with the median marked.
4. **Most expensive PRs/features**: title, repo, cost, merged date, link.
5. **Breakdown**: by team and repo, then model/provider mix.
6. **Coverage and methodology**: the buckets from section 4, the coverage
   figures, and the accuracy caveats in plain language.

Also ship the joined dataset (JSON or CSV) next to the HTML, so any number can
be checked.

Presentation: self-contained HTML (inline CSS, JS and data; no CDN required at
view time), readable in light and dark, printable to PDF, legible on a laptop
screen in a meeting.

---

## 8. Suggested architecture

A four-stage pipeline with plain data between stages, so each stage can be
tested on its own:

```
collect  ->  enrich  ->  model  ->  render
ledger       PRs,        joined     HTML +
entries      teams       dataset    data file
```

- **collect**: for each repo, read `.tkus/**/*.jsonl` from the default branch.
  Use the GitHub API (fetch only the `.tkus/` subtree, to avoid recursive-tree
  truncation on large repos), or a local clone (`git ls-tree` / `git show`).
  Corrupt lines are skipped with a warning, never fatal.
- **enrich**: list PRs and optional team membership. Cache API responses on
  disk so re-runs are cheap and work offline.
- **model**: apply the join and bucket rules (sections 4 and 5). Pure functions,
  no I/O, which is where most tests live.
- **render**: dataset → HTML. No calculations here beyond formatting.

Keep the git host behind a small interface. GitHub comes first, but GitHub
Enterprise or GitLab may follow.

---

## 9. Open decisions (confirm with the user)

| Decision | Suggested default |
|---|---|
| Language | Python 3.10+ (matches tkus and its maintainers) |
| CLI shape | `tkus-vis build (--repo OWNER/NAME \| --org NAME \| --path CLONE) [--since DATE] [--until DATE] -o report.html` |
| GitHub auth | `GITHUB_TOKEN`, falling back to `gh auth token`; read-only scopes |
| Charting | Inline SVG, or an embedded library bundled into the HTML |
| Team mapping source | Config file first; GitHub Teams optional |
| Hosting | GitHub Actions on a schedule, publishing to Pages or a build artifact |
| Org auth at scale | Fine-grained PAT vs. a GitHub App |

---

## 10. Milestones

1. **Local, single repo, no network.** Read the ledger from a local clone,
   bucket by branch, render a minimal HTML report. Reconciliation test against
   `tkus rollup --json` passes.
2. **PR join.** GitHub enrichment, the three buckets, cost per merged PR,
   the most expensive PRs, coverage figures.
3. **Organisation scope.** Many repos, team mapping, team and repo breakdowns.
4. **Scheduled publishing.** CI workflow, API caching, period-over-period
   comparison.

---

## 11. Testing

- **Fixtures**: the real tkus ledger (section 3) plus synthetic edge cases:
  reused branch names, forbidden characters in branch names, renamed branches
  (folded and unfolded),
  `since: null` backlog entries, multiple identities on one branch, corrupt
  lines, unknown fields, mixed currencies, a repo with no ledger.
- **Invariant tests**: bucket totals equal the tree total; summing per-PR costs
  double-counts nothing; per-period totals sum to the overall total.
- **API layer**: tested against recorded responses. No live network in unit
  tests.
- **Render**: a snapshot test of the generated HTML structure, plus a check that
  the page loads with no network access.
