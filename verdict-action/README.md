# verdict-action

**Did this change make my agent worse?** Code changes get CI; prompt, skill,
tool-definition and model changes usually don't. This action runs
[`verdict diff`](https://github.com/dannicolau7/verdict#verdict-diff) on every pull
request, posts the result as a PR comment, and fails the check when the gate in your
`verdict.yaml` is breached.

## Usage

```yaml
# .github/workflows/verdict.yml
name: Verdict
on: pull_request

permissions:
  contents: read
  pull-requests: write

jobs:
  verdict:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: dannicolau7/verdict-action@v1
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

You also need a `verdict.yaml` and a JSONL suite in your repo. See the
[Verdict README](https://github.com/dannicolau7/verdict#verdict-diff).
[`examples/verdict.yml`](examples/verdict.yml) is a fuller workflow with path filters
and concurrency.

## What it does

1. Installs `verdict-eval` and runs
   `verdict diff --base <PR base> --head <PR head>`. If the clone is shallow, it
   fetches full history first.
2. Posts the Markdown result as a PR comment, or updates its earlier comment. It finds
   its own comment by the `<!-- verdict-diff -->` marker. A skipped run (no watched
   files changed) only updates an existing comment and never adds a new one.
3. Writes the same Markdown to the job summary.
4. Fails the check if the gate is breached or `verdict diff` errors.

## Inputs

| Input | Default | Description |
|---|---|---|
| `config` | `verdict.yaml` | Path to the config |
| `base` | PR base SHA | Base ref or SHA |
| `head` | PR head SHA | Head ref or SHA |
| `runs` | from config | Runs per side |
| `anthropic-api-key` | — | Exported as `ANTHROPIC_API_KEY` for the judge |
| `verdict-version` | `0.5.*` | Version, `latest`, or a pip URL such as `git+https://github.com/dannicolau7/verdict@main` |
| `python-version` | `3.12` | Python to run on |
| `comment` | `true` | Post or update the PR comment |
| `github-token` | `github.token` | Token for the comment |

Your agent may need its own secrets. Set them as `env:` on the step and they reach it.

## Outputs

| Output | Values |
|---|---|
| `status` | `completed`, `skipped` or `error` |
| `passed` | `true` if the gate passed or the run was skipped |
| `json-path` | Path to `verdict-diff.json` |
| `markdown-path` | Path to `verdict-diff.md` |

## Notes

- **Fork PRs** get a read-only token and no secrets. The comment step logs a warning
  instead of failing, and the result is still in the job summary. The judge needs an
  API key, so runs from forks only work when nothing watched changed.
- **Cost:** each run calls your agent and the judge `cases × runs × 2` times. Use a
  `paths:` filter (see the example) so unrelated PRs don't start the job at all.

## License

MIT
