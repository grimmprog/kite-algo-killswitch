import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { getSegments, updateSegment } from '../../api/settings';
import type { SegmentStatus } from '../../api/types';

const SEGMENT_LABELS: Record<string, string> = {
  NSE: 'NSE — National Stock Exchange',
  BSE: 'BSE — Bombay Stock Exchange',
  NFO: 'NFO — NSE Futures & Options',
  BFO: 'BFO — BSE Futures & Options',
};

export function SegmentManager() {
  const [segments, setSegments] = useState<SegmentStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [togglingSegment, setTogglingSegment] = useState<string | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const fetchSegments = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await getSegments();
      setSegments(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load segments';
      setFetchError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSegments();
  }, [fetchSegments]);

  const handleToggle = async (segment: string, currentlyActive: boolean) => {
    setTogglingSegment(segment);
    setToggleError(null);
    try {
      const updated = await updateSegment(segment, { is_active: !currentlyActive });
      setSegments((prev) =>
        prev.map((s) => (s.segment === segment ? updated : s))
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : `Failed to toggle ${segment}`;
      setToggleError(message);
    } finally {
      setTogglingSegment(null);
    }
  };

  if (loading) {
    return (
      <Card title="Segment Management">
        <p className="text-sm text-dashboard-muted">Loading segments…</p>
      </Card>
    );
  }

  return (
    <Card title="Segment Management" subtitle="Activate or deactivate trading segments on Zerodha">
      {fetchError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      )}

      {toggleError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {toggleError}
        </div>
      )}

      <div className="space-y-3">
        {segments.map((seg) => (
          <div
            key={seg.segment}
            className="flex items-center justify-between p-3 rounded-lg border border-dashboard-border bg-dashboard-bg/50"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-dashboard-text">
                  {seg.segment}
                </p>
                {seg.deactivated_by_killswitch && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-loss/10 text-loss">
                    Kill Switch
                  </span>
                )}
              </div>
              <p className="text-xs text-dashboard-muted mt-0.5">
                {SEGMENT_LABELS[seg.segment] || seg.segment}
              </p>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={seg.is_active}
              aria-label={`Toggle ${seg.segment} segment`}
              disabled={togglingSegment === seg.segment}
              onClick={() => handleToggle(seg.segment, seg.is_active)}
              className={`
                relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full
                border-2 border-transparent transition-colors duration-200 ease-in-out
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dashboard-bg
                disabled:opacity-50 disabled:cursor-not-allowed
                ${seg.is_active ? 'bg-profit' : 'bg-dashboard-border'}
              `}
            >
              <span
                aria-hidden="true"
                className={`
                  pointer-events-none inline-block h-5 w-5 rounded-full
                  bg-white shadow transform ring-0 transition duration-200 ease-in-out
                  ${seg.is_active ? 'translate-x-5' : 'translate-x-0'}
                `}
              />
            </button>
          </div>
        ))}

        {segments.length === 0 && !fetchError && (
          <p className="text-sm text-dashboard-muted text-center py-4">
            No segments available
          </p>
        )}
      </div>
    </Card>
  );
}
