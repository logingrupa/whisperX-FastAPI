import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Copy, Check } from 'lucide-react';

/**
 * Copy-to-clipboard button (KEY-04 show-once UX).
 * Icon flips to Check for 2s after success — no toast spam (UI-09).
 *
 * Tiger-style: navigator.clipboard.writeText is user-initiated only
 * (button click); plaintext never logged.
 */
export function CopyKeyButton({
  value,
  label = 'Copy',
}: {
  value: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  const onClick = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Button type="button" variant="outline" onClick={onClick} aria-label={label}>
      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
      <span className="ml-2">{copied ? 'Copied' : label}</span>
    </Button>
  );
}
