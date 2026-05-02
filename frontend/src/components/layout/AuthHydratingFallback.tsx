/**
 * Visible placeholder rendered while authStore hydrates the boot probe
 * (`/api/account/me`). Used by RequireAuth, RedirectIfAuthed, and any
 * suspense boundary that depends on auth state.
 *
 * Replaces `return null` so a slow boot probe (network latency, cold-start)
 * never paints a blank page — the user always sees something.
 */
export function AuthHydratingFallback() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-screen items-center justify-center p-6 text-sm text-muted-foreground"
    >
      Loading…
    </div>
  );
}
