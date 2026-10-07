# Security

Please report a vulnerability privately, through
[GitHub's private vulnerability reporting](https://github.com/natekot/tkus-vis/security/advisories/new),
rather than in a public issue.

tkus-vis is read-only toward the repositories it analyses. It reads a GitHub token from
`GITHUB_TOKEN` or `gh auth token`, sends it only to the GitHub API, and never writes it to disk.
Reports about anything that could leak that token, or an email address, are especially welcome.
