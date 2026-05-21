# Contributing to Verdict

Thank you for your interest in contributing to Verdict.

## Scope

Verdict is a **defensive evaluation framework** — it tests AI systems for safety, robustness, and
compliance. Contributions that help evaluate and harden AI systems are welcome. Contributions that
help circumvent AI safety measures are not.

## Security boundary — mandatory reading

### No novel attack research

The adaptive probe generator (`verdict/agents/adaptive_generator.py`) composes probes exclusively
from a curated library of **publicly known** attack patterns sourced from:

- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [NIST AI RMF](https://www.nist.gov/artificial-intelligence)
- Peer-reviewed published research

**Pull requests that do any of the following will be closed without review:**

- Add novel jailbreak techniques not yet publicly disclosed
- Include actual working exploit payloads or synthesis routes for harmful content
- Extend the pattern library with undisclosed techniques
- Modify `select_next_pattern()` to call an LLM for pattern generation
- Remove or weaken the safety boundary language in `ADAPTIVE_SYSTEM_PROMPT`

When adding patterns to `verdict/evals/attack_patterns/patterns.json`, every entry **must**:

1. Have a `source_url` pointing to a publicly accessible document
2. Cite OWASP LLM Top 10, NIST, CVE, CWE, or a peer-reviewed paper in the `source` field
3. Use only the documented template placeholders: `{follow_up}`, `{persona}`, `{other_model}`,
   `{harmful_action}`, `{false_claim}`, `{context}`
4. Not contain actual harmful content (real synthesis routes, working exploits, etc.)

This policy follows **NIST AI RMF GOVERN-6** (responsible disclosure and bounded research scope).

## Development setup

```bash
pip install -e ".[dev]"
```

## Running tests

```bash
# All tests
pytest

# Smoke tests only (fast, no LLM calls)
pytest tests/smoke/ -q

# Unit tests
pytest tests/unit/ -q

# Security boundary tests
pytest tests/security/ -q
```

The security boundary tests in `tests/security/test_adaptive_boundary.py` verify that:
- All patterns in `patterns.json` have public source citations
- No composed probe contains dangerous content
- Pattern selection is rule-based and cannot be escalated beyond the library

## Submitting changes

1. Open an issue to discuss significant changes before implementing them
2. Follow the existing code style (PEP 8, type hints, docstrings)
3. Add or update tests for any changed behavior
4. Ensure `pytest tests/smoke/ tests/unit/ tests/security/` passes before opening a PR

## Reporting vulnerabilities

If you discover a security vulnerability in Verdict itself, please open a GitHub issue marked
**[SECURITY]**. Do not open a public issue for vulnerabilities in third-party systems that
Verdict is used to evaluate — those should be reported to the relevant vendor via their
responsible disclosure process.
