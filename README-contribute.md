# Contributing to odin-bots

```bash
git clone https://github.com/onicai/odin_bots.git
cd odin_bots
make install-dev
make test
```

Note: On macOS Apple Silicon, install `automake` and `libtool` before running `make install-dev`:
```bash
brew install automake libtool
```

# Release Instructions

1. Update the version in `pyproject.toml` and `src/odin_bots/__init__.py`
2. Run `make test` — all tests must pass
3. Publish to PyPI: `make publish`
4. Commit and push to `main`:
   - Commit message must be exactly the version string, e.g. `v0.5.1`
   - Do NOT add co-author lines or any other text
   ```bash
   git add pyproject.toml src/odin_bots/__init__.py
   git commit -m "v0.5.1"
   git push
   ```
5. Tag the release:

```bash
# Get all current tags with their commit sha & description
git fetch --tags
git tag -l --format='%(refname:short) -> %(if)%(*objectname)%(then)%(*objectname:short)%(else)%(objectname:short)%(end) %(contents:subject)'

# Add the tag
RELEASE_TAG=v0.5.0                                          # match pyproject.toml version
RELEASE_SHA=xxxxxxx                                          # get with `git log --oneline -5`
RELEASE_MESSAGE="v0.5.0: multi-bot trading, E2E targets, monitor improvements" # short description of the release
git tag -a $RELEASE_TAG $RELEASE_SHA -m "$RELEASE_MESSAGE"

# Push to GitHub
git push origin $RELEASE_TAG
```
