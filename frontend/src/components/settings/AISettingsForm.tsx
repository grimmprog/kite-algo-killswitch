import { useCallback, useEffect, useState } from 'react';
import { Card } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { getAISettings, updateAISettings } from '../../api/settings';
import type { AISettings } from '../../api/types';

type AIProvider = AISettings['provider'];

interface FeatureToggle {
  key: keyof AISettings;
  label: string;
  description: string;
}

const FEATURE_TOGGLES: FeatureToggle[] = [
  {
    key: 'signal_analysis_enabled',
    label: 'Signal Quality Analysis',
    description: 'AI evaluates scanner signals with quality ratings and warnings',
  },
  {
    key: 'entry_suggestions_enabled',
    label: 'Entry Suggestions',
    description: 'AI suggests optimal entry points and timing',
  },
  {
    key: 'exit_recommendations_enabled',
    label: 'Exit Recommendations',
    description: 'AI evaluates open positions and recommends exit timing',
  },
  {
    key: 'market_narrative_enabled',
    label: 'Market Narrative',
    description: 'AI-generated market context and morning briefs',
  },
  {
    key: 'trade_review_enabled',
    label: 'Trade Review',
    description: 'AI reviews completed trades with improvement suggestions',
  },
  {
    key: 'risk_warnings_enabled',
    label: 'Risk Warnings',
    description: 'Proactive AI warnings about dangerous conditions',
  },
];

export function AISettingsForm() {
  const [settings, setSettings] = useState<AISettings>({
    provider: 'gemini',
    api_key_configured: false,
    signal_analysis_enabled: true,
    entry_suggestions_enabled: true,
    exit_recommendations_enabled: true,
    market_narrative_enabled: true,
    trade_review_enabled: true,
    risk_warnings_enabled: true,
  });
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const data = await getAISettings();
      setSettings(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load AI settings';
      setFetchError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleProviderChange = (provider: AIProvider) => {
    setSettings((prev) => ({ ...prev, provider }));
    setSaveSuccess(false);
  };

  const handleFeatureToggle = (key: keyof AISettings) => {
    setSettings((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      const payload: Partial<AISettings> & { api_key?: string } = {
        provider: settings.provider,
        signal_analysis_enabled: settings.signal_analysis_enabled,
        entry_suggestions_enabled: settings.entry_suggestions_enabled,
        exit_recommendations_enabled: settings.exit_recommendations_enabled,
        market_narrative_enabled: settings.market_narrative_enabled,
        trade_review_enabled: settings.trade_review_enabled,
        risk_warnings_enabled: settings.risk_warnings_enabled,
      };

      // Only include API key if the user typed a new one
      if (apiKeyInput.trim()) {
        (payload as Record<string, unknown>).api_key = apiKeyInput.trim();
      }

      const updated = await updateAISettings(payload);
      setSettings(updated);
      setApiKeyInput('');
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save AI settings';
      setFetchError(message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card title="AI Settings">
        <p className="text-sm text-dashboard-muted">Loading AI settings…</p>
      </Card>
    );
  }

  return (
    <Card title="AI Trading Assistant" subtitle="Configure AI provider, API key, and feature toggles">
      {fetchError && (
        <div role="alert" className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {fetchError}
        </div>
      )}

      <div className="space-y-6">
        {/* Provider Selection */}
        <fieldset>
          <legend className="text-sm font-medium text-dashboard-text mb-2">
            AI Provider
          </legend>
          <div className="flex gap-3">
            {(['gemini', 'claude'] as AIProvider[]).map((provider) => (
              <label
                key={provider}
                className={`
                  flex items-center gap-2 px-4 py-2.5 rounded-lg border cursor-pointer
                  transition-colors duration-150
                  ${
                    settings.provider === provider
                      ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                      : 'border-dashboard-border bg-dashboard-bg/50 text-dashboard-muted hover:text-dashboard-text'
                  }
                `}
              >
                <input
                  type="radio"
                  name="ai-provider"
                  value={provider}
                  checked={settings.provider === provider}
                  onChange={() => handleProviderChange(provider)}
                  className="sr-only"
                />
                <span className="text-sm font-medium capitalize">{provider}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* API Key */}
        <div>
          <Input
            label="API Key"
            type="password"
            value={apiKeyInput}
            onChange={(e) => {
              setApiKeyInput(e.target.value);
              setSaveSuccess(false);
            }}
            placeholder={settings.api_key_configured ? '••••••••••••••••' : 'Enter API key'}
            helperText={
              settings.api_key_configured
                ? 'API key is configured. Enter a new value to replace it.'
                : 'No API key configured. AI features will be unavailable until configured.'
            }
          />
          {settings.api_key_configured && (
            <div className="mt-1 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-profit" aria-hidden="true" />
              <span className="text-xs text-profit">Key configured</span>
            </div>
          )}
        </div>

        {/* Feature Toggles */}
        <fieldset>
          <legend className="text-sm font-medium text-dashboard-text mb-3">
            AI Features
          </legend>
          <div className="space-y-3">
            {FEATURE_TOGGLES.map((feature) => (
              <div
                key={feature.key}
                className="flex items-center justify-between p-3 rounded-lg border border-dashboard-border bg-dashboard-bg/50"
              >
                <div className="flex-1 min-w-0 mr-3">
                  <p className="text-sm font-medium text-dashboard-text">
                    {feature.label}
                  </p>
                  <p className="text-xs text-dashboard-muted mt-0.5">
                    {feature.description}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={!!settings[feature.key]}
                  aria-label={`Toggle ${feature.label}`}
                  onClick={() => handleFeatureToggle(feature.key)}
                  className={`
                    relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full
                    border-2 border-transparent transition-colors duration-200 ease-in-out
                    focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dashboard-bg
                    ${settings[feature.key] ? 'bg-profit' : 'bg-dashboard-border'}
                  `}
                >
                  <span
                    aria-hidden="true"
                    className={`
                      pointer-events-none inline-block h-5 w-5 rounded-full
                      bg-white shadow transform ring-0 transition duration-200 ease-in-out
                      ${settings[feature.key] ? 'translate-x-5' : 'translate-x-0'}
                    `}
                  />
                </button>
              </div>
            ))}
          </div>
        </fieldset>

        {/* Save button */}
        <div className="flex items-center gap-3 pt-2">
          <Button onClick={handleSave} isLoading={saving} disabled={saving}>
            Save AI Settings
          </Button>
          {saveSuccess && (
            <span className="text-sm text-profit" role="status">
              ✓ AI settings saved successfully
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}
