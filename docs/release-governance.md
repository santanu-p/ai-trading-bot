# Release Governance

This repo treats strategy, prompt, execution, and risk-policy changes as controlled releases rather than ordinary refactors.

## Required Release Artifacts

- a release entry in [strategy-change-log.md](strategy-change-log.md)
- replay or equivalent validation evidence
- a rollback plan
- an independently named reviewer for the change

## Repo Guardrails

- pull requests now use the checked-in PR template to capture release ID, reviewer, evidence, rollback plan, and risk summary
- `.github/workflows/release-guard.yml` blocks release-controlled PRs when the PR body is missing those fields or `docs/strategy-change-log.md` is not updated
- the guard applies when changes touch strategy, prompt, execution, worker, or risk-policy files

## What This Does Not Enforce

- GitHub branch protection itself is still a repository-host setting
- required reviewer approvals and code-owner review enforcement still need to be enabled in GitHub settings
- staged rollout policy, environment promotion, and hosted rollback automation remain deployment responsibilities

## Recommended Host Settings

- require the `CI` and `Release Guard` workflows before merge
- require at least one independent reviewer approval for release-controlled changes
- require linear history or squash merges for easier rollback attribution
- restrict direct pushes to the default branch
