import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { getKillSwitchThresholds, updateKillSwitchThresholds } from '../../api/settings';
import { getStrategySettings } from '../../api/settings';
import type { KillSwitchThresholds, ThresholdType } from '../../api/types';

interface FormErrors {
  daily_loss_value?: string;
  profit_target_value?: string;
  drawdown_value?: string;
  profit_warning_pct?: string;
}

function validate(thresholds: KillSwitchThresholds): FormErrors {
  const errors: FormErrors = {};

  if (thresholds.daily_loss_value <= 0) {
    errors.daily_loss_value = 'Must be a positive number';
  }

  if (thresholds.profit_target_value <= 0) {
    errors.profit_target_value = 'Must be a positive number';
  }

  if (thresholds.drawdown_value <= 0) {
    errors.drawdown_value = 'Must be a positive number';
  }

  if (thresholds.profit_warning_pct <= 0) {
    errors.profit_warning_pct = 'Must be a positive number';
  }

  return errors;
}

function TypeToggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: ThresholdType;
  onChange: (type: ThresholdType) => void;
}) {
  return (
    <fieldset className="mb-1">
      <legend className="sr-only">{label} type</legend>
      <div className="flex gap-1 rounded-lg bg-dashboard-bg p-0.5">
        <button
          type="button"
          onClick={() => onChange('amount')}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
            value === 'amount'
              ? 'bg-dashboard-card text-dashboard-text shadow-sm'
              : 'text-dashboard-muted hover:text-dashboard-text'
          }`}
          aria-pressed={value === 'amount'}
        >
          ₹ Amount
        </button>
        <button
          type="button"
          onClick={() => onChange('percentage')}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
            value === 'percentage'
              ? 'bg-dashboard-card text-dashboard-text shadow-sm'
              : 'text-dashboard-muted hover:text-dashboard-text'
          }`}
          aria-pressed={value === 'percentage'}
        >
          % Percentage
        </button>
      </div>
    </fieldset>
  );
}

export function KillSwitchForm() {
  const [thresholds, setThresholds] = useState<KillSwitchThresholds>({
    daily_loss_type: 'amount',
    daily_loss_value: 5000,
    profit_target_type: 'amount',
    profit_target_value: 10000,
    drawdown_type: 'amount',
    drawdown_value: 8000,
    profit_warning_pct: 80,
  });
  const [capital, setCapital] = useState<number>(40000);
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [capitalWarning, setCapitalWarning] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const [thresholdsData, strategyData] = await Promise.all([
        getKillSwitchThresholds(),
        getStrategySettings(),
      ]);
      setThresholds(thresholdsData);
      setCapital(strategyData.capital);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load kill switch settings';
      setFetchError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Check capital warning when daily loss changes
  useEffect(() => {
    let lossAmount = thresholds.daily_loss_value;
    if (thresholds.daily_loss_type === 'percentage') {
      lossAmount = (capital * thresholds.daily_loss_value) / 100;
    }
    if (capital > 0 && lossAmount > capital * 0.25) {
      setCapitalWarning(
        `Daily loss threshold exceeds 25% of capital (₹${(capital * 0.25).toFixed(0)}). This is a high risk setting.`
      );
    } else {
      setCapitalWarning(null);
    }
  }, [thresholds.daily_loss_value, thresholds.daily_loss_type, capital]);

  const handleValueChange = (field: keyof KillSwitchThresholds, value: number) => {
    setThresholds((prev) => ({ ...prev, [field]: value }));
    setSaveSuccess(false);
    setErrors((prev) => ({ ...prev, [field]: undefined }));
  };

  const handleTypeChange = (field: keyof KillSwitchThresholds, type: ThresholdType) => {
    setThresholds((prev) => ({ ...prev, [field]: type }));
    setSaveSuccess(false);
  };

  const getCalculatedAmount = (type: ThresholdType, value: number): string | null => {
    if (type === 'percentage' && capital > 0) {
      return `= ₹${((capital * value) / 100).toFixed(0)}`;
    }
    return null;
  };

  const handleSave = async () => {
    const validationErrors = validate(thresholds);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setSaving(true);
    setSaveSuccess(false);
    try {
      const updated = await updateKillSwitchThresholds(thresholds);
      setThresholds(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save thresholds';
      setFetchError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card title="Kill Switch Thresholds">
        <p className="text-sm text-dashboard-muted">Loading thresholds…</p>
      </Card>
    );
  }

  return (
    <Card title="Kill Switch Thresholds" subtitle="Configure automatic trading halt triggers">
      {fetchError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      )}

      {capitalWarning && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm">
          ⚠ {capitalWarning}
        </div>
      )}

      <div className="space-y-6">
        {/* Daily Loss Threshold */}
        <div>
          <p className="text-sm font-medium text-dashboard-text mb-2">Daily Loss Threshold</p>
          <TypeToggle
            label="Daily loss"
            value={thresholds.daily_loss_type}
            onChange={(type) => handleTypeChange('daily_loss_type', type)}
          />
          <div className="mt-2">
            <Input
              label={thresholds.daily_loss_type === 'amount' ? 'Loss Amount (₹)' : 'Loss Percentage (%)'}
              type="number"
              min={0.01}
              step={thresholds.daily_loss_type === 'percentage' ? 0.5 : 100}
              value={thresholds.daily_loss_value}
              onChange={(e) => handleValueChange('daily_loss_value', parseFloat(e.target.value) || 0)}
              error={errors.daily_loss_value}
              helperText={getCalculatedAmount(thresholds.daily_loss_type, thresholds.daily_loss_value) || undefined}
            />
          </div>
        </div>

        {/* Profit Target Threshold */}
        <div>
          <p className="text-sm font-medium text-dashboard-text mb-2">Profit Target</p>
          <TypeToggle
            label="Profit target"
            value={thresholds.profit_target_type}
            onChange={(type) => handleTypeChange('profit_target_type', type)}
          />
          <div className="mt-2">
            <Input
              label={thresholds.profit_target_type === 'amount' ? 'Target Amount (₹)' : 'Target Percentage (%)'}
              type="number"
              min={0.01}
              step={thresholds.profit_target_type === 'percentage' ? 0.5 : 100}
              value={thresholds.profit_target_value}
              onChange={(e) => handleValueChange('profit_target_value', parseFloat(e.target.value) || 0)}
              error={errors.profit_target_value}
              helperText={getCalculatedAmount(thresholds.profit_target_type, thresholds.profit_target_value) || undefined}
            />
          </div>
        </div>

        {/* Drawdown Threshold */}
        <div>
          <p className="text-sm font-medium text-dashboard-text mb-2">Drawdown Threshold</p>
          <TypeToggle
            label="Drawdown"
            value={thresholds.drawdown_type}
            onChange={(type) => handleTypeChange('drawdown_type', type)}
          />
          <div className="mt-2">
            <Input
              label={thresholds.drawdown_type === 'amount' ? 'Drawdown Amount (₹)' : 'Drawdown Percentage (%)'}
              type="number"
              min={0.01}
              step={thresholds.drawdown_type === 'percentage' ? 0.5 : 100}
              value={thresholds.drawdown_value}
              onChange={(e) => handleValueChange('drawdown_value', parseFloat(e.target.value) || 0)}
              error={errors.drawdown_value}
              helperText={getCalculatedAmount(thresholds.drawdown_type, thresholds.drawdown_value) || undefined}
            />
          </div>
        </div>

        {/* Profit Warning Percentage */}
        <Input
          label="Profit Warning (%)"
          type="number"
          min={1}
          max={100}
          step={5}
          value={thresholds.profit_warning_pct}
          onChange={(e) => handleValueChange('profit_warning_pct', parseFloat(e.target.value) || 0)}
          error={errors.profit_warning_pct}
          helperText="Warn when profit reaches this % of target"
        />

        {/* Save button */}
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} isLoading={saving} disabled={saving}>
            Save Thresholds
          </Button>
          {saveSuccess && (
            <span className="text-sm text-profit" role="status">
              ✓ Thresholds saved and applied
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}
