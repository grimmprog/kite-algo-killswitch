import { useState, useEffect, useCallback } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { useNotifications } from '../hooks/useNotifications';
import type { Notification, NotificationSeverity } from '../hooks/useNotifications';

// --- Constants ---

const PAGE_SIZE = 20;

type SeverityFilter = NotificationSeverity | 'all';

interface FilterOption {
  id: SeverityFilter;
  label: string;
}

const FILTER_OPTIONS: FilterOption[] = [
  { id: 'all', label: 'All' },
  { id: 'critical', label: 'Critical' },
  { id: 'warning', label: 'Warning' },
  { id: 'info', label: 'Info' },
];

// --- Severity styling ---

const severityStyles: Record<NotificationSeverity, { dot: string; bg: string; border: string; badge: string }> = {
  info: {
    dot: 'bg-blue-400',
    bg: 'bg-blue-500/5',
    border: 'border-l-blue-400',
    badge: 'bg-blue-500/10 text-blue-400',
  },
  warning: {
    dot: 'bg-amber-400',
    bg: 'bg-amber-500/5',
    border: 'border-l-amber-400',
    badge: 'bg-amber-500/10 text-amber-400',
  },
  critical: {
    dot: 'bg-red-500',
    bg: 'bg-red-500/5',
    border: 'border-l-red-500',
    badge: 'bg-red-500/10 text-red-400',
  },
};

// --- Helpers ---

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  });
}

function formatFullTimestamp(ts: string): string {
  const date = new Date(ts);
  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// --- Sub-Components ---

function NotificationHistoryItem({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
}) {
  const styles = severityStyles[notification.severity];

  return (
    <div
      className={`
        px-4 py-3 border-l-2 rounded-r-md transition-colors
        ${styles.border} ${styles.bg}
        ${!notification.read ? 'opacity-100' : 'opacity-60'}
      `}
      role="article"
      aria-label={`${notification.severity} notification: ${notification.title}`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`mt-1.5 w-2.5 h-2.5 rounded-full flex-shrink-0 ${styles.dot}`}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <p className="text-sm font-medium text-dashboard-text truncate">
                {notification.title}
              </p>
              <span
                className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium capitalize ${styles.badge}`}
              >
                {notification.severity}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span
                className="text-xs text-dashboard-muted whitespace-nowrap"
                title={formatFullTimestamp(notification.timestamp)}
              >
                {formatTimestamp(notification.timestamp)}
              </span>
              {!notification.read && (
                <button
                  type="button"
                  onClick={() => onMarkRead(notification.id)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors whitespace-nowrap"
                  aria-label={`Mark "${notification.title}" as read`}
                >
                  Mark read
                </button>
              )}
            </div>
          </div>
          <p className="text-sm text-dashboard-muted mt-1">
            {notification.message}
          </p>
          {notification.category && (
            <span className="inline-block mt-1.5 text-[10px] text-dashboard-muted bg-dashboard-border/50 px-1.5 py-0.5 rounded">
              {notification.category}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function SeverityFilterBar({
  activeFilter,
  onFilterChange,
}: {
  activeFilter: SeverityFilter;
  onFilterChange: (filter: SeverityFilter) => void;
}) {
  return (
    <div
      className="flex gap-1 p-1 bg-dashboard-card border border-dashboard-border rounded-lg"
      role="radiogroup"
      aria-label="Filter notifications by severity"
    >
      {FILTER_OPTIONS.map((option) => (
        <button
          key={option.id}
          role="radio"
          aria-checked={activeFilter === option.id}
          onClick={() => onFilterChange(option.id)}
          className={`
            px-3 py-1.5 text-xs font-medium rounded-md transition-colors
            ${
              activeFilter === option.id
                ? 'bg-blue-600 text-white'
                : 'text-dashboard-muted hover:text-dashboard-text hover:bg-dashboard-border/50'
            }
          `}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function PaginationControls({
  currentPage,
  hasMore,
  isLoading,
  onPrevious,
  onNext,
}: {
  currentPage: number;
  hasMore: boolean;
  isLoading: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between pt-4 border-t border-dashboard-border">
      <Button
        variant="secondary"
        size="sm"
        disabled={currentPage === 0 || isLoading}
        onClick={onPrevious}
        aria-label="Previous page"
      >
        ← Previous
      </Button>
      <span className="text-xs text-dashboard-muted">
        Page {currentPage + 1}
      </span>
      <Button
        variant="secondary"
        size="sm"
        disabled={!hasMore || isLoading}
        onClick={onNext}
        aria-label="Next page"
      >
        Next →
      </Button>
    </div>
  );
}

// --- Main Page Component ---

export function NotificationsPage() {
  const { fetchNotifications, markAsRead, markAllAsRead, isLoading, error } = useNotifications();

  const [allNotifications, setAllNotifications] = useState<Notification[]>([]);
  const [activeFilter, setActiveFilter] = useState<SeverityFilter>('all');
  const [currentPage, setCurrentPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);

  // Fetch page of notifications
  const loadPage = useCallback(async (page: number) => {
    setPageLoading(true);
    const offset = page * PAGE_SIZE;
    const result = await fetchNotifications(offset, PAGE_SIZE);
    setAllNotifications(result);
    setHasMore(result.length === PAGE_SIZE);
    setPageLoading(false);
  }, [fetchNotifications]);

  // Load initial page
  useEffect(() => {
    loadPage(0);
  }, [loadPage]);

  // Handle page changes
  const handleNextPage = useCallback(() => {
    const nextPage = currentPage + 1;
    setCurrentPage(nextPage);
    loadPage(nextPage);
  }, [currentPage, loadPage]);

  const handlePreviousPage = useCallback(() => {
    const prevPage = Math.max(0, currentPage - 1);
    setCurrentPage(prevPage);
    loadPage(prevPage);
  }, [currentPage, loadPage]);

  // Handle filter changes (reset to page 0)
  const handleFilterChange = useCallback((filter: SeverityFilter) => {
    setActiveFilter(filter);
    setCurrentPage(0);
    loadPage(0);
  }, [loadPage]);

  // Handle mark as read
  const handleMarkRead = useCallback(async (notificationId: string) => {
    await markAsRead(notificationId);
    setAllNotifications((prev) =>
      prev.map((n) => (n.id === notificationId ? { ...n, read: true } : n))
    );
  }, [markAsRead]);

  // Handle mark all as read
  const handleMarkAllRead = useCallback(() => {
    markAllAsRead();
    setAllNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, [markAllAsRead]);

  // Filter notifications by severity
  const filteredNotifications = activeFilter === 'all'
    ? allNotifications
    : allNotifications.filter((n) => n.severity === activeFilter);

  const unreadCount = allNotifications.filter((n) => !n.read).length;
  const loading = isLoading || pageLoading;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Notifications</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              Full notification history across all events
            </p>
          </div>
          {unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleMarkAllRead}
              aria-label="Mark all notifications as read"
            >
              Mark all read ({unreadCount})
            </Button>
          )}
        </div>

        {/* Filters */}
        <div className="flex items-center justify-between gap-4">
          <SeverityFilterBar
            activeFilter={activeFilter}
            onFilterChange={handleFilterChange}
          />
          {unreadCount > 0 && (
            <span className="text-xs text-dashboard-muted">
              {unreadCount} unread
            </span>
          )}
        </div>

        {/* Error state */}
        {error && (
          <Card className="border-loss/30 bg-loss/5" role="alert" aria-live="assertive">
            <div className="flex items-start gap-3">
              <span className="text-loss text-lg" aria-hidden="true">⚠</span>
              <div>
                <p className="text-sm font-medium text-loss">Failed to load notifications</p>
                <p className="text-xs text-dashboard-muted mt-0.5">{error}</p>
              </div>
            </div>
          </Card>
        )}

        {/* Loading state */}
        {loading && filteredNotifications.length === 0 && (
          <Card className="flex items-center justify-center py-12" role="status" aria-live="polite">
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
              <p className="text-sm text-dashboard-muted">Loading notifications...</p>
            </div>
          </Card>
        )}

        {/* Empty state */}
        {!loading && !error && filteredNotifications.length === 0 && (
          <Card>
            <div className="text-center py-12">
              <div className="text-3xl mb-3" aria-hidden="true">🔔</div>
              <p className="text-sm text-dashboard-muted">
                {activeFilter === 'all'
                  ? 'No notifications yet'
                  : `No ${activeFilter} notifications`}
              </p>
              <p className="text-xs text-dashboard-muted mt-1">
                Notifications from scanner signals, trades, and system events will appear here
              </p>
            </div>
          </Card>
        )}

        {/* Notification list */}
        {filteredNotifications.length > 0 && (
          <Card padding="none">
            <div
              className="divide-y divide-dashboard-border/50"
              role="feed"
              aria-label="Notification history"
              aria-busy={loading}
            >
              {filteredNotifications.map((notification) => (
                <div key={notification.id} className="px-2 py-1 first:pt-2 last:pb-2">
                  <NotificationHistoryItem
                    notification={notification}
                    onMarkRead={handleMarkRead}
                  />
                </div>
              ))}
            </div>

            {/* Pagination */}
            <div className="px-4 pb-4">
              <PaginationControls
                currentPage={currentPage}
                hasMore={hasMore}
                isLoading={loading}
                onPrevious={handlePreviousPage}
                onNext={handleNextPage}
              />
            </div>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}
