---
slug: forge-deploy-tsc-http-proxy
status: resolved
trigger: Laravel Forge auto-deploy fails on whisper.kingdom.lv with TS2307/TS7006 errors in vite.config.ts during `tsc -b && vite build`. Tunnel exited code 2.
created: 2026-05-05
updated: 2026-05-05
---

# Symptoms

<!-- DATA_START: user-supplied -->
- expected: Forge auto-deploy succeeds, frontend builds cleanly on the server.
- actual: Build step `tsc -b && vite build --base=/` fails. Forge reports "Tunnel exited with a non-zero code [2]". Site whisper.kingdom.lv not deployed.
- error_messages: |
    vite.config.ts(87,35): error TS2307: Cannot find module 'http-proxy' or its corresponding type declarations.
    vite.config.ts(88,33): error TS7006: Parameter 'proxyReq' implicitly has an 'any' type.
    vite.config.ts(88,43): error TS7006: Parameter 'req' implicitly has an 'any' type.
- timeline: Surfaced on this Forge deploy run (Tue May 5 10:09:40 AM UTC 2026). Local `bun run build` presumed clean; Forge runs npm install (461 packages added).
- reproduction: Push to main → Forge webhook clones repo → runs deploy script which executes `npm install` then `tsc -b && vite build --base=/` in frontend/.
<!-- DATA_END -->

# Current Focus

- hypothesis: vite.config.ts imports type from `http-proxy` package which is NOT in frontend/package.json dependencies or devDependencies. `@types/http-proxy` also missing. tsc strict typecheck fails because module declaration cannot be resolved.
- test: grep frontend/package.json for `http-proxy` — expect zero matches.
- expecting: zero matches confirms missing devDep is root cause.
- next_action: RESOLVED — fix applied (Option A: HttpProxy.ProxyServer from vite re-export).
- reasoning_checkpoint:
- tdd_checkpoint:

# Evidence

- timestamp: 2026-05-05
  observation: vite.config.ts:87 contains `configure: (proxy: import('http-proxy').default) => {` and uses inline import type. Line 88 destructures `(proxyReq, req)` callback params which inherit any-type when parent type fails to resolve.
  source: Read tool on frontend/vite.config.ts

- timestamp: 2026-05-05
  observation: frontend/package.json has NO `http-proxy` and NO `@types/http-proxy` in dependencies or devDependencies.
  source: Read tool on frontend/package.json

- timestamp: 2026-05-05
  observation: CLAUDE.md mandates frontend is bun-only; introducing npm artifacts forbidden. Forge log shows `npm install ... added 461 packages` — Forge deploy script using npm not bun.
  source: CLAUDE.md + Forge deploy log

- timestamp: 2026-05-05
  observation: Bug ALSO reproduces locally under bun. `cd frontend && bun run build` emits identical TS2307 + 2× TS7006. Hypothesis "transitive hoist masks issue locally" was wrong — reality is dev mode skips tsc, so nobody noticed until Forge ran the build script.
  source: Bash run of `bun run build` in frontend/

- timestamp: 2026-05-05
  observation: Vite v7 bundles its proxy types from `http-proxy-3` (NOT `http-proxy`) directly in `node_modules/vite/dist/node/index.d.ts`. Vite re-exports the entire namespace as `HttpProxy` and the interface `ProxyOptions` (line 514 + line 3713 of index.d.ts). `ProxyOptions['configure']` is typed `(proxy: ProxyServer, options: ProxyOptions) => void`.
  source: Read of node_modules/vite/dist/node/index.d.ts

- timestamp: 2026-05-05
  observation: `node_modules/http-proxy` and `node_modules/@types/http-proxy` do NOT exist in frontend/. The bare specifier in vite.config.ts has never resolved — bug latent since proxy `configure` was added.
  source: ls of node_modules subdirs

# Eliminated

- "Forge npm vs local bun divergence" — bug reproduces identically under bun locally. Package manager is not the cause; missing type import is.
- "Add @types/http-proxy as devDep" — would mask the real problem (Vite uses http-proxy-3, not http-proxy). Would also pull an unrelated type tree into the project and still leave a phantom runtime dep reference.

# Resolution

- root_cause: vite.config.ts:87 referenced `import('http-proxy').default` for the proxy `configure` callback parameter. The `http-proxy` package is not (and was never) installed in frontend/ — Vite v7 internally uses `http-proxy-3` and bundles its types under the re-exported `HttpProxy` namespace. `tsc -b` strict mode failed to resolve the bare module specifier, cascading to implicit-any on the inner callback params. Bug was latent because dev mode (`vite`) skips tsc; only `build` runs the typecheck, and the `configure` hook was added without a build verification.

- fix: Replaced `import('http-proxy').default` with Vite's first-party `HttpProxy.ProxyServer` type (added `type HttpProxy` to the existing `from 'vite'` import). Zero new dependencies, idiomatic Vite-native typing, works under any package manager (bun OR npm). Added comment explaining the choice for future maintainers.

- verification: `cd frontend && bun run build` passes cleanly. `tsc -b` emits no errors; `vite build` produces the full asset graph (1990 modules transformed, 16.00s, all dist/ chunks emitted). Forge deploy will succeed because the bare `'http-proxy'` specifier no longer exists — only types from `vite` (always installed) are referenced.

- files_changed:
  - frontend/vite.config.ts (import: added `type HttpProxy`; line 87: `proxy: HttpProxy.ProxyServer` replaces `proxy: import('http-proxy').default`; added explanatory comment block above httpProxy const)

# Followup (informational, no action taken)

- Forge deploy script uses `npm install` while CLAUDE.md mandates bun-only for frontend. Lockfile-of-record is `bun.lock`; running npm on the server can drift from local resolution and silently introduce divergent transitive versions. Recommend switching the Forge deploy script to `bun install --frozen-lockfile && bun run build` (requires bun to be available on the Forge server). Not changed in this session — needs explicit user approval and Forge-side configuration.
