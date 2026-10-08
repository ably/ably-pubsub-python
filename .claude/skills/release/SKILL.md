---
description: "Create a release branch, bump version, and update CHANGELOG. Usage: /release patch|minor|major"
allowed-tools: Bash, Read, Edit, Write
---

Read the current version from `pyproject.toml` (the `version` property).

The bump type is: $ARGUMENTS

Compute the new version by incrementing the appropriate component of the current version:
- `patch` — increment the third number, keep major and minor (e.g. 1.7.0 → 1.7.1)
- `minor` — increment the second number, reset patch to 0 (e.g. 1.7.0 → 1.8.0)
- `major` — increment the first number, reset minor and patch to 0 (e.g. 1.7.0 → 2.0.0)

Then perform these steps in order:

1. Run `git checkout -b release/NEW_VERSION`
2. Replace `OLD_VERSION` with `NEW_VERSION` in all of the following files:
    - `pyproject.toml` — the `version` property
    - `ably/pubsub/version.py` — lib_version value
      3.Run `uv sync` to update `uv.lock` file
4. Commit all files together with message: `chore: bump version to NEW_VERSION`
3. Fetch merged PRs since the last release tag using:
   ```
   gh pr list --state merged --base main --json number,title,mergedAt --limit 200
   ```
   Then get the date of the last release tag with:
   ```
   git log vOLD_VERSION --format="%aI" -1
   ```
   Filter the PRs to only those merged after that tag date. Format each as:
   ```
   - Short, one sentence summary from PR title and description [#NUMBER](https://github.com/ably/ably-pubsub-python/pull/NUMBER)
   ```
   If the tag doesn't exist or there are no merged PRs, use a single `-` placeholder bullet instead.

4. In `CHANGELOG.md`, insert the following block immediately after the `# Change Log` heading (and its trailing blank line), before the first existing `## [` version entry:

```
## [NEW_VERSION](https://github.com/ably/ably-pubsub-python/tree/vNEW_VERSION)

[Full Changelog](https://github.com/ably/ably-pubsub-python/compare/vOLD_VERSION...vNEW_VERSION)

### What's Changed

BULLETS_FROM_STEP_3

```

5. Commit `CHANGELOG.md` with message: `docs: update CHANGELOG for NEW_VERSION release`

After completing all steps, show the user a summary of what was done. If PRs were found, list them. If the placeholder `-` was used instead, remind them to fill in the `### What's Changed` bullet points in `CHANGELOG.md` before merging.
