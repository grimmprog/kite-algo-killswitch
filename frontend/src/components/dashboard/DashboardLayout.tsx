import { useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useWebSocket } from '../../contexts/WebSocketContext';

interface DashboardLayoutProps {
  children: ReactNode;
}

const NAV_ITEMS = [
  { path: '/dashboard', label: 'Dashboard', icon: '📊' },
  { path: '/scanner', label: 'Scanner', icon: '🔍' },
  { path: '/analysis', label: 'Index Analysis', icon: '🎯' },
  { path: '/positions', label: 'Positions', icon: '📈' },
  { path: '/trade', label: 'New Trade', icon: '💹' },
  { path: '/trades', label: 'Trade History', icon: '📋' },
  { path: '/journal', label: 'Journal', icon: '📓' },
  { path: '/paper-trading', label: 'Paper Trading', icon: '📝' },
  { path: '/notifications', label: 'Notifications', icon: '🔔' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
];

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const { user, logout } = useAuth();
  const { isConnected } = useWebSocket();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-dashboard-bg flex">
      {/* Sidebar - mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-64 bg-dashboard-card border-r border-dashboard-border
          transform transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:z-auto
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        aria-label="Main navigation"
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-4 border-b border-dashboard-border">
            <h2 className="text-lg font-bold text-dashboard-text">Kite Algo</h2>
            <p className="text-xs text-dashboard-muted">Trading Platform</p>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-3 space-y-1">
            {NAV_ITEMS.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setSidebarOpen(false)}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium
                    transition-colors duration-150
                    ${isActive
                      ? 'bg-blue-600/10 text-blue-500 border border-blue-500/20'
                      : 'text-dashboard-muted hover:text-dashboard-text hover:bg-dashboard-bg'
                    }
                  `}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <span aria-hidden="true">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* User info */}
          <div className="p-4 border-t border-dashboard-border">
            <p className="text-sm text-dashboard-text truncate">{user?.email}</p>
            <button
              onClick={logout}
              className="mt-2 text-xs text-dashboard-muted hover:text-loss transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="sticky top-0 z-30 bg-dashboard-card border-b border-dashboard-border px-4 py-3 flex items-center justify-between">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 rounded-lg text-dashboard-muted hover:text-dashboard-text hover:bg-dashboard-bg"
            aria-label="Open navigation menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="flex items-center gap-3 ml-auto">
            {/* Connection status */}
            <div className="flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${isConnected ? 'bg-profit' : 'bg-loss'}`}
                aria-hidden="true"
              />
              <span className="text-xs text-dashboard-muted">
                {isConnected ? 'Live' : 'Disconnected'}
              </span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
