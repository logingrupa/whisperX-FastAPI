import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, KeyRound, Trash2 } from 'lucide-react';
import { fetchKeys, type ApiKeyListItem } from '@/lib/api/keysApi';
import { ApiClientError, RateLimitError } from '@/lib/apiClient';
import { CreateKeyDialog } from '@/components/dashboard/CreateKeyDialog';
import { RevokeKeyDialog } from '@/components/dashboard/RevokeKeyDialog';

/**
 * Keys dashboard (UI-05).
 *
 * Dumb orchestrator (SRP):
 *   - keysApi  -> HTTP via apiClient (DRY)
 *   - CreateKeyDialog / RevokeKeyDialog -> modal state machines
 *   - this page wires them: fetch -> render -> open modal -> on success refresh
 *
 * `/frontend-design` UI-13: header + clear table + empty state CTA;
 * generous gap-6; rounded-xl Card; destructive variant on revoke; status Badge.
 */
export function KeysDashboardPage() {
  const [keys, setKeys] = useState<ApiKeyListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<{ id: number; name: string } | null>(null);

  const refresh = async () => {
    setError(null);
    try {
      const list = await fetchKeys();
      setKeys(list);
    } catch (err) {
      // RateLimitError BEFORE ApiClientError — RateLimitError extends ApiClientError
      if (err instanceof RateLimitError) {
        setError(`Rate limited. Try again in ${err.retryAfterSeconds}s.`);
        return;
      }
      if (err instanceof ApiClientError) {
        setError('Could not load keys.');
        return;
      }
      setError('Could not load keys.');
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  // active first, then by created_at desc — most-recent active key on top
  const sortedKeys = (keys ?? []).slice().sort((a, b) => {
    if (a.status !== b.status) return a.status === 'active' ? -1 : 1;
    return b.created_at.localeCompare(a.created_at);
  });

  const isEmpty = keys !== null && keys.length === 0;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">API keys</h1>
          <p className="text-sm text-muted-foreground">
            Use these to authenticate the WhisperX HTTP API.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          <span className="ml-2">Create key</span>
        </Button>
      </div>

      {error !== null && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {isEmpty && (
        <Card className="flex flex-col items-center gap-3 p-12 text-center">
          <KeyRound className="h-8 w-8 text-muted-foreground" />
          <p className="font-medium">No keys yet</p>
          <p className="text-sm text-muted-foreground">
            Create your first API key to start your free trial.
          </p>
          <Button className="mt-2" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" />
            <span className="ml-2">Create key</span>
          </Button>
        </Card>
      )}

      {!isEmpty && keys !== null && (
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40">
              <tr className="text-left">
                <th className="p-3 font-medium">Name</th>
                <th className="p-3 font-medium">Prefix</th>
                <th className="p-3 font-medium">Created</th>
                <th className="p-3 font-medium">Last used</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium" aria-label="actions" />
              </tr>
            </thead>
            <tbody>
              {sortedKeys.map((k) => (
                <tr key={k.id} className="border-b border-border last:border-0">
                  <td className="p-3 font-medium">{k.name}</td>
                  <td className="p-3 font-mono text-xs">{k.prefix}…</td>
                  <td className="p-3">{new Date(k.created_at).toLocaleDateString()}</td>
                  <td className="p-3">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="p-3">
                    <Badge variant={k.status === 'active' ? 'default' : 'secondary'}>
                      {k.status}
                    </Badge>
                  </td>
                  <td className="p-3 text-right">
                    {k.status === 'active' && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setRevokeTarget({ id: k.id, name: k.name })}
                        aria-label={`Revoke ${k.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                        <span className="ml-1">Revoke</span>
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <CreateKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => {
          refresh();
        }}
      />
      <RevokeKeyDialog
        keyId={revokeTarget?.id ?? null}
        keyName={revokeTarget?.name ?? null}
        open={revokeTarget !== null}
        onOpenChange={(o) => {
          if (!o) setRevokeTarget(null);
        }}
        onRevoked={() => {
          setRevokeTarget(null);
          refresh();
        }}
      />
    </div>
  );
}
