# Distribution & release runbook

How `marketplaces-mcp-ru` reaches users, and the exact steps to cut a release.
Five channels, one repo:

| Channel | Who | Artifact | How it's built |
| --- | --- | --- | --- |
| **`.mcpb` bundle** | Non-technical sellers on Claude Desktop | `dist/*.mcpb` | `scripts/package_mcpb.py`, attached to the GitHub Release |
| **GitHub zip** | Sellers who prefer download-and-click installers | `dist/*.zip` | `scripts/package_release.py`, attached to the Release |
| **PyPI / `uvx`** | Developers & agencies | `marketplaces-mcp-ru` on PyPI | `publish-pypi.yml` on every `v*` tag (OIDC Trusted Publishing) |
| **Docker / GHCR** | Servers, agencies, anyone without Python | `ghcr.io/ilyautov/marketplaces-mcp-ru:<version>` | `publish-registry.yml` on every `v*` tag |
| **MCP Registry** | Discovery inside MCP clients | `server.json` metadata (PyPI + OCI packages) | `publish-registry.yml` via GitHub OIDC after PyPI is live; manual `mcp-publisher` as fallback |

All five are backed by the **combined server** (`core/combined.py`): WB + Ozon +
Ozon Performance on one FastMCP (58 tools). `uvx marketplaces-mcp-ru` and the
`.mcpb` both run it; `wb-mcp` / `ozon-mcp` / `ozon-perf-mcp` remain available
for running a single service.

---

## One-time setup (do these once, before the first release)

### 1. PyPI Trusted Publishing (pending publisher)

The `publish-pypi.yml` workflow uses OIDC — no token is stored anywhere. PyPI
must be told to trust it. Because the package does not exist yet, register a
**pending publisher**:

1. Log in to <https://pypi.org> → account menu → **Publishing**.
2. **Add a pending publisher** with exactly:
   - PyPI Project Name: `marketplaces-mcp-ru`
   - Owner: `ilyautov`
   - Repository name: `marketplaces-mcp-ru`
   - Workflow name: `publish-pypi.yml`  ← the filename, not the workflow's `name:`
   - Environment name: `pypi`
3. Save. It converts to a permanent publisher on the first successful run.

> The name is not reserved until the first publish. If someone else claims
> `marketplaces-mcp-ru` on PyPI first, the pending publisher is invalidated.

### 2. GHCR package visibility (once, after the first image push)

`publish-registry.yml` pushes with the workflow's `GITHUB_TOKEN`. A personal
account's first push creates the package **private**, and the registry cannot
verify a private image. After the first run: GitHub → your profile → Packages →
`marketplaces-mcp-ru` → Package settings → **Change visibility → Public**. Then
re-run the workflow (`workflow_dispatch` with the tag) so the `registry` job
succeeds. Later releases need nothing.

### 3. MCP Registry ownership marker

Already in place: `README.md` carries `<!-- mcp-name: io.github.ilyautov/marketplaces-mcp-ru -->`.
That comment becomes the PyPI long description, and the registry scrapes it to
confirm you own the PyPI package. Keep it in the README.

---

## Cutting a release

1. Bump the version in **`pyproject.toml`** (single source of truth). The
   `.mcpb` packer syncs `mcpb/manifest.json` to it automatically; update
   `server.json`'s `version` (and the package `version`) to match by hand.
2. Update `CHANGELOG.md`.
3. Commit, then tag and push:
   ```bash
   git tag v0.3.2
   git push origin v0.3.2
   ```
4. The tag triggers three workflows automatically:
   - **`release.yml`** → builds the zip and the `.mcpb`, attaches both to the
     GitHub Release.
   - **`publish-pypi.yml`** → builds sdist+wheel, publishes to PyPI via OIDC.
   - **`publish-registry.yml`** → builds the OCI image, pushes
     `ghcr.io/ilyautov/marketplaces-mcp-ru:<version>` and `:latest`, smoke-tests
     it with a real `docker run`, waits for PyPI to serve the version, then
     publishes `server.json` to the MCP Registry via GitHub OIDC.
5. Verify: `uvx marketplaces-mcp-ru doctor`, `docker run --rm ghcr.io/ilyautov/marketplaces-mcp-ru:<version> doctor`,
   and the listing at `https://registry.modelcontextprotocol.io/v0/servers?search=marketplaces-mcp-ru`.

`tests/test_versions.py` fails the build if `pyproject.toml`, `server.json`
(both package entries) and `mcpb/manifest.json` disagree on the version, and if
the Dockerfile's `io.modelcontextprotocol.server.name` label drifts from
`server.json`'s `name`.

---

## Publishing to the MCP Registry by hand (fallback)

Normally `publish-registry.yml` does this. If it failed (PyPI late, GHCR still
private), fix the cause and re-run the workflow, or publish manually. The registry
hosts metadata only and validates that the PyPI package and the OCI image exist,
so publish **after** both are live:

```bash
# install the publisher CLI (macOS)
brew install mcp-publisher     # or download from the registry releases page

# from the repo root (server.json lives here)
mcp-publisher login github      # opens a device-code prompt
mcp-publisher publish --dry-run # validate server.json only
mcp-publisher publish           # publish the listing
```

`server.json`'s `name` must stay under the `io.github.ilyautov/` namespace —
that's what GitHub auth authorizes. Bump `version` and both package `version`
fields on each release before re-publishing.

---

## Local build checks (no publishing)

```bash
python3 scripts/package_mcpb.py --list          # build + inspect the .mcpb
npx -y @anthropic-ai/mcpb validate mcpb/manifest.json
python3 -m build                                # build sdist+wheel locally
python3 serve.py all --selfcheck                # combined server smoke test
python3 serve.py doctor                         # tools, catalogs, keys
docker build -t marketplaces-mcp-ru . && docker run --rm marketplaces-mcp-ru doctor
```
