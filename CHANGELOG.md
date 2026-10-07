# Changelog

All notable changes to tkus-vis are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Until 1.0, a minor version may change the
command line or the dataset.

## [Unreleased]

## [0.1.0] - 2026-10-07

The first public release: milestones 1 and 2 of the design brief.

### Added

- `tkus-vis build`: a self-contained HTML report of a repository's tkus ledger, with its
  dataset as JSON. Totals reconcile with `tkus rollup --json`.
- `tkus-vis slides`: finished 16:9 infographics as 2x PNG and vector PDF, ready to paste into
  a deck. Slides that overflow are flagged. Needs macOS and Google Chrome.
- `--repo OWNER/NAME`: reads the ledger and pull requests through read-only GitHub API calls,
  then adds cost per merged PR (median and spread), the most expensive PRs, spend against
  merged PRs, and coverage to the slides and the dataset. The HTML report shows only the
  buckets so far.
- Every dollar lands in exactly one bucket: PR-attributed, direct to the default branch, or
  unmatched.

[Unreleased]: https://github.com/natekot/tkus-vis/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/natekot/tkus-vis/releases/tag/v0.1.0
