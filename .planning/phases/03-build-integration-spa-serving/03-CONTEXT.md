# Phase 3: Build Integration & SPA Serving - Context

**Gathered:** 2026-01-27
**Status:** Ready for planning

<domain>
## Phase Boundary

React SPA builds and serves correctly from FastAPI at /ui route. Users can access the frontend, refresh any page without 404, and development mode works smoothly. No Docker — build locally, commit dist, server pulls.

</domain>

<decisions>
## Implementation Decisions

### Route structure
- Claude's discretion on nested routes vs single-page (will determine based on Phase 4-6 features)
- Claude's discretion on 404 handling within React app
- Claude's discretion on trailing slash behavior
- Claude's discretion on API route accessibility

### Dev workflow
- Single command starts both frontend and backend together
- Claude's discretion on where the command lives (root vs frontend package.json)
- Claude's discretion on frontend folder name
- Claude's discretion on hot-reload coordination between Vite and uvicorn

### Build output
- **No Docker** — simple deployment without containers
- Build locally, commit dist/ to repo, server just pulls
- Server deployment: git pull, restart service (no build step on server)
- Claude's discretion on dist/ location (frontend/dist/ vs app/static/ui/)
- No pre-commit hooks for build reminders

### Loading states
- App skeleton while React/JS loads (gray placeholder shapes)
- Claude's discretion on skeleton implementation (inline HTML vs React component)
- Friendly "modern browser required" message if JavaScript fails
  - Casual tone: "Hey! This app needs a modern browser..."
  - Beautiful page, not just text

### Claude's Discretion
- Nested routes vs single-page architecture (based on features in Phase 4-6)
- 404 handling strategy
- Trailing slash behavior
- Frontend folder naming
- Hot-reload coordination approach
- Dist folder location
- Skeleton implementation method

</decisions>

<specifics>
## Specific Ideas

- Friendly/casual tone for browser requirement message — matches the app's approachable feel
- Beautiful fallback page for no-JS users, not just a plain text message
- Keep deployment simple: git pull on server, no build steps there

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-build-integration-spa-serving*
*Context gathered: 2026-01-27*
