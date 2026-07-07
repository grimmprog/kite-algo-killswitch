import { useCallback, useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { updateAutoLogin } from '../../api/settings';
import type { KiteStatusResponse } from '../../api/types';
import { AxiosError } from 'axios';

interface AutoLoginConfigProps {
  kiteStatus: KiteStatusResponse;
  onUpdated: () => void;
}

/**
 * Auto-Login configuration sub-component for the Kite Connection Panel.
 * Provides TOTP key input (masked), enable/disable toggle, and last attempt display.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8
 */
export function AutoLoginConfig({ kiteStatus, onUpdated }: AutoLoginConfigProps) {
  const [enabled, setEnabled] = useState(kiteStatus.auto_login_enabled);
  const [totpKey, setTotpKey] = useState('');
  const [isEditing, setIsEditing] = useState(!kiteStatus.key_configured);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Sync state when kiteStatus changes externally
  useEffect(() => {
    setEnabled(kiteStatus.auto_login_enabled);
    setIsEditing(!kiteStatus.key_configured);
  }, [kiteStatus.auto_login_enabled, kiteStatus.key_configured]);

  const handleToggle = useCallback(() => {
    setEnabled((prev) => !prev);
    setSaveSuccess(false);
    setError(null);
  }, []);

  const handleChangeClick = useCallback(() => {
    setIsEditing(true);
    setTotpKey('');
    setError(null);
    setSaveSuccess(false);
  }, []);

  const handleSave = useCallback(async () => {
    setError(null);
    setSaving(true);
    setSaveSuccess(false);

    try {
      const request = {
        totp_key: isEditing && totpKey.trim() ? totpKey.trim() : null,
        enabled,
      };

      await updateAutoLogin(request);
      setSaveSuccess(true);
      setTotpKey('');
      setIsEditing(false);
      onUpdated();
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      if (err instanceof AxiosError && err.response?.status === 422) {
        const detail = err.response.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Invalid TOTP key format');
      } else {
        const message = err instanceof Error ? err.message : 'Failed to save auto-login settings';
        setError(message);
      }
    } finally {
      setSaving(false);
    }
  }, [enabled, isEditing, totpKey, onUpdated]);

  return (
    <div className="space-y-4 pt-3 border-t border-dashboard-border">
      <h4 className="text-sm font-medium text-dashboard-text">Auto-Login Configuration</h4>

      {/* TOTP Key Input */}
      <div>
        {kiteStatus.key_configured && !isEditing ? (
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium text-dashboard-text mb-1.5">
                Google Authenticator TOTP Key
              </label>
              <div className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-muted text-sm font-mono">
                ••••••••••••
              </div>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleChangeClick}
              className="mt-6"
            >
              Change
            </Button>
          </div>
        ) : (
          <Input
            label="Google Authenticator TOTP Key"
            type="password"
            value={totpKey}
            onChange={(e) => {
              setTotpKey(e.target.value);
              setError(null);
              setSaveSuccess(false);
            }}
            placeholder="Enter your Zerodha TOTP secret key"
            error={error && error.includes('TOTP') ? error : undefined}
            helperText="Base32 secret from Zerodha's 2FA setup (same key used in Google Authenticator)"
          />
        )}
      </div>

      {/* Enable Auto-Login Toggle */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-sm font-medium text-dashboard-text">Enable Auto-Login</span>
          <p className="text-xs text-dashboard-muted mt-0.5">
            Automatically re-authenticate daily at 8:45 AM IST
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={handleToggle}
          className={`
            relative inline-flex h-6 w-11 items-center rounded-full
            transition-colors duration-200 ease-in-out
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dashboard-bg
            ${enabled ? 'bg-blue-600' : 'bg-dashboard-border'}
          `}
        >
          <span className="sr-only">Enable Auto-Login</span>
          <span
            aria-hidden="true"
            className={`
              inline-block h-4 w-4 rounded-full bg-white shadow-sm
              transition-transform duration-200 ease-in-out
              ${enabled ? 'translate-x-6' : 'translate-x-1'}
            `}
          />
        </button>
      </div>

      {/* Last Auto-Login Result */}
      {kiteStatus.last_auto_login_at && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-dashboard-muted">Last Auto-Login</span>
          <span className="text-dashboard-text">
            {kiteStatus.last_auto_login_at}
            {kiteStatus.last_auto_login_success !== null && (
              <span
                className={`ml-2 ${kiteStatus.last_auto_login_success ? 'text-profit' : 'text-loss'}`}
              >
                {kiteStatus.last_auto_login_success ? '✓ Success' : '✗ Failed'}
              </span>
            )}
          </span>
        </div>
      )}

      {/* Error display (non-TOTP errors) */}
      {error && !error.includes('TOTP') && (
        <div role="alert" className="p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm">
          {error}
        </div>
      )}

      {/* Save Button */}
      <div className="flex items-center gap-3">
        <Button
          onClick={handleSave}
          isLoading={saving}
          disabled={saving}
          size="sm"
        >
          Save Auto-Login
        </Button>
        {saveSuccess && (
          <span className="text-sm text-profit" role="status">
            ✓ Auto-login settings saved
          </span>
        )}
      </div>
    </div>
  );
}
