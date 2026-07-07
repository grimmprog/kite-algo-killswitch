import { useState } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useScanner } from '../hooks/useScanner';
import type { ScanSignal } from '../hooks/useScanner';

type TabId = 'trend-pullback' | 'consolidation';

interface Tab {
  id: TabId;
  label: string;
}

const TABS: Tab[] = [
  { id: 'trend-pullback', label: 'Trend Pullback' },
  { id: 'consolidation', label: 'Consolidation' },
];

function ScanResultsTable({ signals }: { signals: ScanSignal[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label="Scan results">
        <thead>
          <tr className="border-b border-dashboard-border">
            <th className="text-left py-2 px-2 text-xs text-dashboard-muted font-medium">
              Symbol
            </th>
            <th className="text-right py-2 px-2 text-xs text-dashboard-muted font-medium">
              Confidence
            </th>
            <th className="text-right py-2 px-2 text-xs text-dashboard-muted font-medium">
              Entry
            </th>
            <th className="text-right py-2 px-2 text-xs text-dashboard-muted font-medium">
              Stop Loss
            </th>
            <th className="text-right py-2 px-2 text-xs text-dashboard-muted font-medium">
              Target
            </th>
            <th className="text-right py-2 px-2 text-xs text-dashboard-muted font-medium">
              Max Loss
            </th>
          </tr>
        </thead>
        <tbody>
          {signals.map((signal) => (
            <tr
              key={signal.id}
              className="border-b border-dashboard-border last:border-0 hover:bg-dashboard-bg/50 transition-colors"
            >
              <td className="py-2.5 px-2 font-mono font-medium text-dashboard-text">
                {signal.symbol}
              </td>
              <td className="py-2.5 px-2 text-right">
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    signal.confidenceScore >= 80
                      ? 'bg-profit/10 text-profit'
                      : signal.confidenceScore >= 65
                        ? 'bg-yellow-500/10 text-yellow-400'
                        : 'bg-dashboard-border text-dashboard-muted'
                  }`}
                >
                  {signal.confidenceScore}
                </span>
              </td>
              <td className="py-2.5 px-2 text-right font-mono text-dashboard-text">
                ₹{signal.entryPrice.toFixed(2)}
              </td>
              <td className="py-2.5 px-2 text-right font-mono text-loss">
                ₹{signal.stopLoss.toFixed(2)}
              </td>
              <td className="py-2.5 px-2 text-right font-mono text-profit">
                ₹{signal.targetPrice.toFixed(2)}
              </td>
              <td className="py-2.5 px-2 text-right font-mono text-loss">
                ₹{signal.maxPotentialLoss.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrendPullbackTab() {
  const { signals, isScanning, scanError, lastScanTime, triggerTrendPullbackScan } =
    useScanner();

  const trendSignals = signals.filter((s) => s.scanType === 'trend_pullback');

  return (
    <div className="space-y-4">
      {/* Scan trigger */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-dashboard-text">
            Trend Pullback Scanner
          </h3>
          <p className="text-xs text-dashboard-muted mt-0.5">
            Scan watchlist for trend-pullback setups with confidence scoring
          </p>
        </div>
        <Button
          onClick={triggerTrendPullbackScan}
          isLoading={isScanning}
          disabled={isScanning}
          aria-label="Trigger trend pullback scan"
        >
          {isScanning ? 'Scanning...' : 'Scan'}
        </Button>
      </div>

      {/* Loading indicator */}
      {isScanning && (
        <Card className="flex items-center justify-center py-8" role="status" aria-live="polite">
          <div className="flex flex-col items-center gap-3">
            <svg
              className="animate-spin h-6 w-6 text-blue-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <p className="text-sm text-dashboard-muted">
              Scanning watchlist for trend-pullback setups...
            </p>
          </div>
        </Card>
      )}

      {/* Error message */}
      {scanError && !isScanning && (
        <Card
          className="border-loss/30 bg-loss/5"
          role="alert"
          aria-live="assertive"
        >
          <div className="flex items-start gap-3">
            <span className="text-loss text-lg" aria-hidden="true">⚠</span>
            <div>
              <p className="text-sm font-medium text-loss">Scan failed</p>
              <p className="text-xs text-dashboard-muted mt-0.5">{scanError}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Results */}
      {!isScanning && !scanError && trendSignals.length === 0 && lastScanTime && (
        <Card>
          <div className="text-center py-6">
            <p className="text-sm text-dashboard-muted">No setups found</p>
            <p className="text-xs text-dashboard-muted mt-1">
              Last scanned: {new Date(lastScanTime).toLocaleTimeString()}
            </p>
          </div>
        </Card>
      )}

      {!isScanning && trendSignals.length > 0 && (
        <Card padding="none">
          <div className="px-4 pt-4 pb-2 flex items-center justify-between">
            <h4 className="text-sm font-medium text-dashboard-text">
              {trendSignals.length} signal{trendSignals.length !== 1 ? 's' : ''} found
            </h4>
            {lastScanTime && (
              <span className="text-xs text-dashboard-muted">
                {new Date(lastScanTime).toLocaleTimeString()}
              </span>
            )}
          </div>
          <ScanResultsTable signals={trendSignals} />
        </Card>
      )}
    </div>
  );
}

function ConsolidationTab() {
  return (
    <Card>
      <div className="text-center py-8">
        <p className="text-sm text-dashboard-muted">
          Consolidation scanner coming soon
        </p>
      </div>
    </Card>
  );
}

export function ScannerPage() {
  const [activeTab, setActiveTab] = useState<TabId>('trend-pullback');

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-bold text-dashboard-text">Scanner</h1>
          <p className="text-sm text-dashboard-muted mt-1">
            Scan for trading setups across your watchlist
          </p>
        </div>

        {/* Tabs */}
        <div
          className="flex border-b border-dashboard-border"
          role="tablist"
          aria-label="Scanner tabs"
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`
                px-4 py-2.5 text-sm font-medium transition-colors duration-150
                border-b-2 -mb-px
                ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-500'
                    : 'border-transparent text-dashboard-muted hover:text-dashboard-text'
                }
              `}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab panels */}
        <div
          role="tabpanel"
          id={`panel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
        >
          {activeTab === 'trend-pullback' && <TrendPullbackTab />}
          {activeTab === 'consolidation' && <ConsolidationTab />}
        </div>
      </div>
    </DashboardLayout>
  );
}
