---
status: diagnosed
trigger: "Investigate the TUS cleanup scheduler date parsing error"
created: 2026-01-31T00:00:00Z
updated: 2026-01-31T00:15:00Z
---

## Current Focus

hypothesis: CONFIRMED - tuspyserver writes RFC 7231 dates but gc_files() uses fromisoformat() which only accepts ISO 8601
test: examine all date handling code in tuspyserver
expecting: found root cause and identified solution approach
next_action: document root cause and fix strategy

## Symptoms

expected: TUS cleanup scheduler should parse expires dates and clean up expired uploads
actual: Backend startup fails with ValueError during TUS upload cleanup
errors: "ValueError: Invalid isoformat string: 'Fri, 30 Jan 2026 18:16:01 GMT'" at tuspyserver/file.py line 127
reproduction: start backend, scheduler runs cleanup_expired_uploads on startup
started: discovered during Test 5 of backend validation

## Eliminated

## Evidence

- timestamp: 2026-01-31T00:05:00Z
  checked: tuspyserver/routes/creation.py line 228
  found: expires field is set using `_format_rfc7231_date(date_expiry)` which calls `formatdate(dt.timestamp(), usegmt=True)` - this produces RFC 2822/7231 format like "Fri, 30 Jan 2026 18:16:01 GMT"
  implication: tuspyserver writes expires dates in RFC 7231 format (RFC 2822 compatible)

- timestamp: 2026-01-31T00:06:00Z
  checked: tuspyserver/file.py line 127
  found: `datetime.datetime.fromisoformat(file.info.expires)` - fromisoformat() only accepts ISO 8601 format, not RFC 2822/7231
  implication: gc_files() attempts to parse RFC 7231 dates with a function that expects ISO 8601 - this is the bug

- timestamp: 2026-01-31T00:07:00Z
  checked: tuspyserver/routes/core.py lines 16-40
  found: _check_upload_expired() function properly handles both RFC 7231 and ISO 8601 formats using parsedate_to_datetime from email.utils
  implication: tuspyserver already has code that correctly parses RFC 7231 dates, but gc_files() doesn't use it

- timestamp: 2026-01-31T00:10:00Z
  checked: tuspyserver/lock.py entire file
  found: lock.py has platform-specific patches for fcntl→msvcrt on Windows (lines 18-25), demonstrating that the project already patches tuspyserver for platform compatibility
  implication: patching tuspyserver library files directly is an established pattern in this codebase

- timestamp: 2026-01-31T00:12:00Z
  checked: app/infrastructure/scheduler/cleanup_scheduler.py lines 46-62
  found: cleanup_scheduler calls gc_files() directly with no date preprocessing, exception is caught with generic Exception handler
  implication: the cleanup scheduler has no opportunity to fix the date format before it reaches gc_files()

## Resolution

root_cause: |
  tuspyserver has an internal inconsistency in date format handling:

  1. WRITES expires dates in RFC 7231 format (creation.py line 228 and core.py line 249):
     - Uses formatdate(dt.timestamp(), usegmt=True) from email.utils
     - Produces: "Fri, 30 Jan 2026 18:16:01 GMT"

  2. READS expires dates with ISO 8601 parser (file.py line 127):
     - Uses datetime.fromisoformat(file.info.expires)
     - Only accepts: "2026-01-30T18:16:01" or similar ISO 8601 formats

  This is a library bug in tuspyserver itself, not a configuration issue.

  The library already has correct date parsing code in core.py (_check_upload_expired)
  that uses parsedate_to_datetime from email.utils, but gc_files() doesn't use it.

fix: |
  RECOMMENDED: Patch tuspyserver/file.py directly (following established pattern)

  Justification:
  1. The codebase already patches tuspyserver (lock.py has fcntl→msvcrt patches)
  2. Cannot fix in cleanup_scheduler.py because gc_files() reads .info files internally
  3. The fix is simple: replace fromisoformat() with parsedate_to_datetime()

  Alternative approaches considered:
  - Preprocess dates in cleanup_scheduler: NOT VIABLE - gc_files reads files internally
  - Submit upstream PR to tuspyserver: VIABLE but slow, doesn't fix immediate issue
  - Create wrapper function: OVERLY COMPLEX - would need to duplicate gc_files logic

  Patch location: .venv/Lib/site-packages/tuspyserver/file.py line 127

  Change needed:
  FROM: datetime.datetime.fromisoformat(file.info.expires)
  TO:   parsedate_to_datetime(file.info.expires) with proper imports

  This matches the pattern used in core.py's _check_upload_expired() function.

verification:
files_changed: []
