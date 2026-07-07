import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { getMarketDataSources, updateMarketDataSources } from '../../api/settings';
import type { DataSourceConfig, DataSourcesResponse } from '../../api/types';

export function MarketDataTab() {
  const [sources, setSources] = useState<DataSourceConfig[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data: DataSourcesResponse = await getMarketDataSources();
      setSources(data.sources);
      setWarnings(data.warnings);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load market data sources';
      setFetchError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
  }, [fetchSources]);

  const handleToggle = (sourceId: string) => {
    setSources((prev) =>
      prev.map((s) => (s.source_id === sourceId ? { ...s, enabled: !s.enabled } : s))
    );
    setSaveSuccess(false);
    setValidationError(null);
  };

  const handleMoveUp = (index: number) => {
    if (index <= 0) return;
    setSources((prev) => {
      const updated = [...prev];
      // Swap priorities
      const tempPriority = updated[index].priority;
      updated[index] = { ...updated[index], priority: updated[index - 1].priority };
      updated[index - 1] = { ...updated[index - 1], priority: tempPriority };
      // Swap positions
      [updated[index], updated[index - 1]] = [updated[index - 1], updated[index]];
      return updated;
    });
    setSaveSuccess(false);
  };

  const handleMoveDown = (index: number) => {
    if (index >= sources.length - 1) return;
    setSources((prev) => {
      const updated = [...prev];
      // Swap priorities
      const tempPriority = updated[index].priority;
      updated[index] = { ...updated[index], priority: updated[index + 1].priority };
      updated[index + 1] = { ...updated[index + 1], priority: tempPriority };
      // Swap positions
      [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
      return updated;
    });
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    // Validate: at least one source enabled
    const hasEnabled = sources.some((s) => s.enabled);
    if (!hasEnabled) {
      setValidationError('At least one data source must be enabled');
      return;
    }
    setValidationError(null);

    setSaving(true);
    setSaveSuccess(false);
    try {
      const data = await updateMarketDataSources({ sources });
      setSources(data.sources);
      setWarnings(data.warnings);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save market data sources';
      setFetchError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card title="Market Data Sources">
        <p className="text-sm text-dashboard-muted">Loading market data sources…</p>
      </Card>
    );
  }

  return (
    <Card title="Market Data Sources" subtitle="Configure and prioritize your market data providers">
      {fetchError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mb-4 space-y-2">
          {warnings.map((warning, idx) => (
            <div
              key={idx}
              role="alert"
              className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm flex items-start gap-2"
            >
              <span aria-hidden="true" className="flex-shrink-0 mt-0.5">⚠️</span>
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2">
        {sources.map((source, index) => (
          <div
            key={source.source_id}
            className="flex items-center justify-between p-3 rounded-lg border border-dashboard-border bg-dashboard-bg/50"
          >
            {/* Priority controls */}
            <div className="flex items-center gap-1 mr-3">
              <button
                type="button"
                onClick={() => handleMoveUp(index)}
                disabled={index === 0}
                aria-label={`Move ${source.display_name} up`}
                className="p-1 rounded text-dashboard-muted hover:text-dashboard-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                ▲
              </button>
              <button
                type="button"
                onClick={() => handleMoveDown(index)}
                disabled={index === sources.length - 1}
                aria-label={`Move ${source.display_name} down`}
                className="p-1 rounded text-dashboard-muted hover:text-dashboard-text disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                ▼
              </button>
            </div>

            {/* Source info */}
            <div className="flex-1 min-w-0 mr-3">
              <p className="text-sm font-medium text-dashboard-text">
                {source.display_name}
              </p>
              <p className="text-xs text-dashboard-muted mt-0.5">
                Priority: {index + 1}
              </p>
            </div>

            {/* Toggle */}
            <button
              type="button"
              role="switch"
              aria-checked={source.enabled}
              aria-label={`Toggle ${source.display_name}`}
              onClick={() => handleToggle(source.source_id)}
              className={`
                relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full
                border-2 border-transparent transition-colors duration-200 ease-in-out
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dashboard-bg
                ${source.enabled ? 'bg-profit' : 'bg-dashboard-border'}
              `}
            >
              <span
                aria-hidden="true"
                className={`
                  pointer-events-none inline-block h-5 w-5 rounded-full
                  bg-white shadow transform ring-0 transition duration-200 ease-in-out
                  ${source.enabled ? 'translate-x-5' : 'translate-x-0'}
                `}
              />
            </button>
          </div>
        ))}
      </div>

      {/* Validation error */}
      {validationError && (
        <div role="alert" className="mt-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {validationError}
        </div>
      )}

      {/* Save button */}
      <div className="flex items-center gap-3 pt-4">
        <Button onClick={handleSave} isLoading={saving} disabled={saving}>
          Save Data Sources
        </Button>
        {saveSuccess && (
          <span className="text-sm text-profit" role="status">
            ✓ Market data sources saved successfully
          </span>
        )}
      </div>
    </Card>
  );
}
