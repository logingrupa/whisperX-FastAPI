/**
 * QueueFilterBar — search + status filter + pagination controls
 * for the transcribe queue (Plan 15-ux).
 *
 * SRP: this component owns ONLY the input UI. Query state lives in the
 * parent (TranscribePage) and is funneled into useTaskHistory; this
 * component receives current values + change callbacks.
 *
 * Debouncing: q input fires onQueryChange after 300ms idle so each
 * keystroke does NOT trigger a fetch. setTimeout — no new dep.
 *
 * No nested-if: every branch is early-return / flat ternary.
 *
 * /frontend-design polish: gap-3, flex-wrap on mobile, sticky-friendly
 * spacing above the queue list.
 */
import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

/** Sentinel for "no status filter" — empty string is reserved for input. */
export const ALL_STATUSES = 'all';

/** Status filter values surfaced by the bar. */
export type StatusFilter = 'all' | 'processing' | 'completed' | 'failed';

interface QueueFilterBarProps {
  /** Current substring search value. */
  searchQuery: string;
  /** Fired after the debounce window elapses. */
  onSearchQueryChange: (value: string) => void;
  /** Current status filter (use ALL_STATUSES for no filter). */
  statusFilter: StatusFilter;
  /** Fired immediately on Select change. */
  onStatusFilterChange: (value: StatusFilter) => void;
  /** 1-indexed current page. */
  currentPage: number;
  /** Total pages (>= 1). */
  totalPages: number;
  /** Fired with the new 1-indexed page number; bounded by parent. */
  onPageChange: (page: number) => void;
  /** Optional debounce window in ms (defaults to 300). */
  debounceMs?: number;
}

const DEFAULT_DEBOUNCE_MS = 300;

/**
 * Filter / pagination bar above FileQueueList.
 *
 * Self-explanatory naming: searchQuery / statusFilter / currentPage /
 * totalPages mirror the parent's state names so grep returns one hit
 * per concept across page + bar + hook.
 */
export function QueueFilterBar({
  searchQuery,
  onSearchQueryChange,
  statusFilter,
  onStatusFilterChange,
  currentPage,
  totalPages,
  onPageChange,
  debounceMs = DEFAULT_DEBOUNCE_MS,
}: QueueFilterBarProps) {
  // Local input state so the user sees keystrokes without waiting on
  // the debounce — parent only learns the final value.
  const [draft, setDraft] = useState<string>(searchQuery);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Re-sync local draft when the parent's searchQuery changes (e.g. cleared
  // externally). Only push on actual divergence to avoid feedback loops.
  useEffect(() => {
    setDraft(previous => (previous === searchQuery ? previous : searchQuery));
  }, [searchQuery]);

  // Cleanup pending timer on unmount.
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, []);

  function handleDraftChange(next: string): void {
    setDraft(next);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onSearchQueryChange(next);
    }, debounceMs);
  }

  const safeTotalPages = totalPages < 1 ? 1 : totalPages;
  const canGoPrevious = currentPage > 1;
  const canGoNext = currentPage < safeTotalPages;

  return (
    <div
      className="flex flex-wrap items-center gap-3"
      data-testid="queue-filter-bar"
    >
      <Input
        type="search"
        placeholder="Search filename..."
        value={draft}
        onChange={event => handleDraftChange(event.target.value)}
        className="max-w-xs flex-1"
        data-testid="queue-filter-search"
        aria-label="Search filename"
      />

      <Select
        value={statusFilter}
        onValueChange={value => onStatusFilterChange(value as StatusFilter)}
      >
        <SelectTrigger
          className="w-[160px]"
          data-testid="queue-filter-status"
          aria-label="Filter by status"
        >
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_STATUSES}>All statuses</SelectItem>
          <SelectItem value="processing">Processing</SelectItem>
          <SelectItem value="completed">Completed</SelectItem>
          <SelectItem value="failed">Failed</SelectItem>
        </SelectContent>
      </Select>

      <div className="ml-auto flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canGoPrevious}
          onClick={() => onPageChange(currentPage - 1)}
          data-testid="queue-filter-prev"
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span
          className="text-muted-foreground text-sm"
          data-testid="queue-filter-page-indicator"
        >
          Page {currentPage} of {safeTotalPages}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!canGoNext}
          onClick={() => onPageChange(currentPage + 1)}
          data-testid="queue-filter-next"
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
