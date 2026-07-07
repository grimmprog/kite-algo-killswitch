import { useState, useEffect } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { StrategyForm } from '../components/settings/StrategyForm';
import { KillSwitchForm } from '../components/settings/KillSwitchForm';
import { SegmentManager } from '../components/settings/SegmentManager';
import { AISettingsForm } from '../components/settings/AISettingsForm';
import { MarketDataTab } from '../components/settings/MarketDataTab';
import { BrokersTab } from '../components/settings/BrokersTab';

type TabId = 'strategy' | 'killswitch' | 'segments' | 'ai' | 'brokers' | 'marketdata';

interface Tab {
  id: TabId;
  label: string;
  icon: string;
}

const TABS: Tab[] = [
  { id: 'strategy', label: 'Strategy', icon: '📊' },
  { id: 'killswitch', label: 'Kill Switch', icon: '🛑' },
  { id: 'segments', label: 'Segments', icon: '🔀' },
  { id: 'ai', label: 'AI Assistant', icon: '🤖' },
  { id: 'brokers', label: 'Brokers', icon: '🔗' },
  { id: 'marketdata', label: 'Market Data', icon: '📈' },
];

const SESSION_STORAGE_KEY = 'settings-active-tab';

const VALID_TAB_IDS: Set<string> = new Set(TABS.map((t) => t.id));

function getInitialTab(): TabId {
  try {
    const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (stored && VALID_TAB_IDS.has(stored)) {
      return stored as TabId;
    }
  } catch {
    // sessionStorage unavailable (e.g., private browsing restrictions)
  }
  return 'strategy';
}

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>(getInitialTab);

  useEffect(() => {
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, activeTab);
    } catch {
      // sessionStorage unavailable
    }
  }, [activeTab]);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page header */}
        <div>
          <h1 className="text-xl font-bold text-dashboard-text">Settings</h1>
          <p className="text-sm text-dashboard-muted mt-1">
            Configure strategy parameters, risk controls, segments, AI features, broker connections, and market data
          </p>
        </div>

        {/* Tabs */}
        <div
          className="flex border-b border-dashboard-border overflow-x-auto"
          role="tablist"
          aria-label="Settings tabs"
        >
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              id={`settings-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls={`settings-panel-${tab.id}`}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors duration-150
                border-b-2 -mb-px whitespace-nowrap
                ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-500'
                    : 'border-transparent text-dashboard-muted hover:text-dashboard-text'
                }
              `}
            >
              <span aria-hidden="true">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab panels */}
        <div
          role="tabpanel"
          id={`settings-panel-${activeTab}`}
          aria-labelledby={`settings-tab-${activeTab}`}
        >
          {activeTab === 'strategy' && <StrategyForm />}
          {activeTab === 'killswitch' && <KillSwitchForm />}
          {activeTab === 'segments' && <SegmentManager />}
          {activeTab === 'ai' && <AISettingsForm />}
          {activeTab === 'brokers' && <BrokersTab />}
          {activeTab === 'marketdata' && (
            <MarketDataTab />
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
