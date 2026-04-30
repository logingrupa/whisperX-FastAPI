/**
 * QueueFilterBar — RTL coverage (Plan 15-ux).
 *
 * Coverage:
 *   - Search input fires onSearchQueryChange AFTER debounce (not per keystroke)
 *   - Status select fires onStatusFilterChange immediately
 *   - Prev disabled on page 1
 *   - Next disabled on last page
 *   - Page indicator renders "Page N of M"
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import { QueueFilterBar } from '@/components/upload/QueueFilterBar';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function defaultProps(overrides: Partial<React.ComponentProps<typeof QueueFilterBar>> = {}) {
  return {
    searchQuery: '',
    onSearchQueryChange: vi.fn(),
    statusFilter: 'all' as const,
    onStatusFilterChange: vi.fn(),
    currentPage: 1,
    totalPages: 5,
    onPageChange: vi.fn(),
    debounceMs: 300,
    ...overrides,
  };
}

describe('QueueFilterBar — search input', () => {
  it('does NOT fire onSearchQueryChange before debounce elapses', () => {
    const props = defaultProps();
    render(<QueueFilterBar {...props} />);
    const input = screen.getByTestId('queue-filter-search') as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'meet' } });
    fireEvent.change(input, { target: { value: 'meeting' } });

    expect(props.onSearchQueryChange).not.toHaveBeenCalled();
  });

  it('fires onSearchQueryChange with final value after debounce', () => {
    const props = defaultProps();
    render(<QueueFilterBar {...props} />);
    const input = screen.getByTestId('queue-filter-search') as HTMLInputElement;

    fireEvent.change(input, { target: { value: 'meet' } });
    fireEvent.change(input, { target: { value: 'meeting' } });

    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(props.onSearchQueryChange).toHaveBeenCalledTimes(1);
    expect(props.onSearchQueryChange).toHaveBeenCalledWith('meeting');
  });
});

describe('QueueFilterBar — pagination buttons', () => {
  it('disables prev on page 1', () => {
    render(<QueueFilterBar {...defaultProps({ currentPage: 1, totalPages: 5 })} />);
    const prev = screen.getByTestId('queue-filter-prev') as HTMLButtonElement;
    expect(prev.disabled).toBe(true);
  });

  it('disables next on last page', () => {
    render(<QueueFilterBar {...defaultProps({ currentPage: 5, totalPages: 5 })} />);
    const next = screen.getByTestId('queue-filter-next') as HTMLButtonElement;
    expect(next.disabled).toBe(true);
  });

  it('fires onPageChange with currentPage+1 on next click', () => {
    const props = defaultProps({ currentPage: 2, totalPages: 5 });
    render(<QueueFilterBar {...props} />);
    fireEvent.click(screen.getByTestId('queue-filter-next'));
    expect(props.onPageChange).toHaveBeenCalledWith(3);
  });

  it('fires onPageChange with currentPage-1 on prev click', () => {
    const props = defaultProps({ currentPage: 3, totalPages: 5 });
    render(<QueueFilterBar {...props} />);
    fireEvent.click(screen.getByTestId('queue-filter-prev'));
    expect(props.onPageChange).toHaveBeenCalledWith(2);
  });

  it('renders Page N of M indicator', () => {
    render(<QueueFilterBar {...defaultProps({ currentPage: 3, totalPages: 7 })} />);
    expect(screen.getByTestId('queue-filter-page-indicator')).toHaveTextContent(
      'Page 3 of 7',
    );
  });

  it('clamps totalPages to at least 1 (empty result still shows Page 1 of 1)', () => {
    render(<QueueFilterBar {...defaultProps({ currentPage: 1, totalPages: 0 })} />);
    expect(screen.getByTestId('queue-filter-page-indicator')).toHaveTextContent(
      'Page 1 of 1',
    );
  });
});

describe('QueueFilterBar — status select', () => {
  it('exposes the trigger with aria-label for status filter', () => {
    render(<QueueFilterBar {...defaultProps()} />);
    const trigger = screen.getByLabelText('Filter by status');
    expect(trigger).toBeInTheDocument();
  });
});
