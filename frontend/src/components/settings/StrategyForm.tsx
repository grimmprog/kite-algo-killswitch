import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { getStrategySettings, updateStrategySettings } from '../../api/settings';
import type { StrategySettings } from '../../api/types';

interface FormErrors {
  confidence_threshold?: string;
  max_trades_per_day?: string;
  max_active_trades?: string;
  capital?: string;
  trading_start_time?: string;
  trading_end_time?: string;
  watchlist?: string;
}

function validate(settings: StrategySettings): FormErrors {
  const errors: FormErrors = {};

  if (settings.confidence_threshold < 50 || settings.confidence_threshold > 100) {
    errors.confidence_threshold = 'Must be between 50 and 100';
  }

  if (settings.max_trades_per_day < 1 || settings.max_trades_per_day > 10) {
    errors.max_trades_per_day = 'Must be between 1 and 10';
  }

  if (settings.max_active_trades < 1 || settings.max_active_trades > 5) {
    errors.max_active_trades = 'Must be between 1 and 5';
  }

  if (settings.capital <= 0) {
    errors.capital = 'Must be a positive number';
  }

  if (!settings.trading_start_time) {
    errors.trading_start_time = 'Required';
  }

  if (!settings.trading_end_time) {
    errors.trading_end_time = 'Required';
  }

  if (settings.trading_start_time && settings.trading_end_time) {
    if (settings.trading_start_time >= settings.trading_end_time) {
      errors.trading_end_time = 'End time must be after start time';
    }
  }

  if (settings.watchlist.length === 0) {
    errors.watchlist = 'At least one symbol is required';
  }

  return errors;
}

export function StrategyForm() {
  const [settings, setSettings] = useState<StrategySettings>({
    watchlist: [],
    trading_start_time: '09:15',
    trading_end_time: '15:15',
    confidence_threshold: 70,
    max_trades_per_day: 5,
    max_active_trades: 3,
    capital: 40000,
    lot_sizes: { NIFTY: 25, BANKNIFTY: 15, SENSEX: 10 },
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [watchlistInput, setWatchlistInput] = useState('');

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await getStrategySettings();
      setSettings(data);
      setWatchlistInput(data.watchlist.join(', '));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load strategy settings';
      setFetchError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleChange = (field: keyof StrategySettings, value: string | number) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
    setSaveSuccess(false);
    // Clear error for the field
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const handleLotSizeChange = (index: string, value: string) => {
    const numVal = parseInt(value, 10);
    if (!isNaN(numVal) && numVal > 0) {
      setSettings((prev) => ({
        ...prev,
        lot_sizes: { ...prev.lot_sizes, [index]: numVal },
      }));
    }
    setSaveSuccess(false);
  };

  const handleWatchlistChange = (value: string) => {
    setWatchlistInput(value);
    const symbols = value
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0);
    setSettings((prev) => ({ ...prev, watchlist: symbols }));
    setErrors((prev) => ({ ...prev, watchlist: undefined }));
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    const validationErrors = validate(settings);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setSaving(true);
    setSaveSuccess(false);
    try {
      const updated = await updateStrategySettings(settings);
      setSettings(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings';
      setFetchError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card title="Strategy Settings">
        <p className="text-sm text-dashboard-muted">Loading settings…</p>
      </Card>
    );
  }

  return (
    <Card title="Strategy Settings" subtitle="Configure watchlist, time windows, and trading limits">
      {fetchError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      )}

      <div className="space-y-5">
        {/* Watchlist */}
        <Input
          label="Watchlist (comma-separated)"
          value={watchlistInput}
          onChange={(e) => handleWatchlistChange(e.target.value)}
          placeholder="NIFTY, BANKNIFTY, SENSEX"
          error={errors.watchlist}
          helperText="Enter symbols separated by commas"
        />

        {/* Trading Times */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Trading Start Time"
            type="time"
            value={settings.trading_start_time}
            onChange={(e) => handleChange('trading_start_time', e.target.value)}
            error={errors.trading_start_time}
          />
          <Input
            label="Trading End Time"
            type="time"
            value={settings.trading_end_time}
            onChange={(e) => handleChange('trading_end_time', e.target.value)}
            error={errors.trading_end_time}
          />
        </div>

        {/* Confidence & Max Trades */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input
            label="Confidence Threshold"
            type="number"
            min={50}
            max={100}
            value={settings.confidence_threshold}
            onChange={(e) => handleChange('confidence_threshold', parseInt(e.target.value, 10) || 0)}
            error={errors.confidence_threshold}
            helperText="50 – 100"
          />
          <Input
            label="Max Trades / Day"
            type="number"
            min={1}
            max={10}
            value={settings.max_trades_per_day}
            onChange={(e) => handleChange('max_trades_per_day', parseInt(e.target.value, 10) || 0)}
            error={errors.max_trades_per_day}
            helperText="1 – 10"
          />
          <Input
            label="Max Active Trades"
            type="number"
            min={1}
            max={5}
            value={settings.max_active_trades}
            onChange={(e) => handleChange('max_active_trades', parseInt(e.target.value, 10) || 0)}
            error={errors.max_active_trades}
            helperText="1 – 5"
          />
        </div>

        {/* Capital */}
        <Input
          label="Capital (₹)"
          type="number"
          min={1}
          value={settings.capital}
          onChange={(e) => handleChange('capital', parseFloat(e.target.value) || 0)}
          error={errors.capital}
          helperText="Total trading capital"
        />

        {/* Lot Sizes */}
        <div>
          <p className="text-sm font-medium text-dashboard-text mb-2">Lot Sizes</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {Object.entries(settings.lot_sizes).map(([idx, size]) => (
              <Input
                key={idx}
                label={idx}
                type="number"
                min={1}
                value={size}
                onChange={(e) => handleLotSizeChange(idx, e.target.value)}
              />
            ))}
          </div>
        </div>

        {/* Save button */}
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} isLoading={saving} disabled={saving}>
            Save Strategy Settings
          </Button>
          {saveSuccess && (
            <span className="text-sm text-profit" role="status">
              ✓ Settings saved successfully
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}
