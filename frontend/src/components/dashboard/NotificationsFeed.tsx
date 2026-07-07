import { useNotifications } from '../../hooks/useNotifications';
import { Card } from '../ui/Card';
import type { Notification, NotificationSeverity } from '../../hooks/useNotifications';

const severityStyles: Record<NotificationSeverity, { dot: string; bg: string; border: string }> = {
  info: {
    dot: 'bg-blue-400',
    bg: 'bg-blue-500/5',
    border: 'border-l-blue-400',
  },
  warning: {
    dot: 'bg-amber-400',
    bg: 'bg-amber-500/5',
    border: 'border-l-amber-400',
  },
  critical: {
    dot: 'bg-red-500',
    bg: 'bg-red-500/5',
    border: 'border-l-red-500',
  },
};

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

function NotificationItem({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: (id: string) => void;
}) {
  const styles = severityStyles[notification.severity];

  return (
    <button
      type="button"
      onClick={() => !notification.read && onMarkRead(notification.id)}
      className={`
        w-full text-left px-3 py-2 border-l-2 rounded-r-md transition-colors
        ${styles.border} ${styles.bg}
        ${!notification.read ? 'opacity-100' : 'opacity-60'}
        hover:opacity-100
      `}
      aria-label={`${notification.severity} notification: ${notification.title}`}
    >
      <div className="flex items-start gap-2">
        <span
          className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${styles.dot}`}
          aria-hidden="true"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-dashboard-text truncate">
              {notification.title}
            </p>
            <span className="text-[10px] text-dashboard-muted whitespace-nowrap">
              {formatTimestamp(notification.timestamp)}
            </span>
          </div>
          <p className="text-xs text-dashboard-muted mt-0.5 line-clamp-2">
            {notification.message}
          </p>
        </div>
      </div>
    </button>
  );
}

export function NotificationsFeed() {
  const { notifications, unreadCount, markAsRead } = useNotifications();

  return (
    <Card title="Notifications" subtitle={unreadCount > 0 ? `${unreadCount} unread` : undefined}>
      <div className="space-y-1 max-h-80 overflow-y-auto" role="feed" aria-label="Notifications feed">
        {notifications.length === 0 ? (
          <p className="text-xs text-dashboard-muted text-center py-4">
            No notifications yet
          </p>
        ) : (
          notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              onMarkRead={markAsRead}
            />
          ))
        )}
      </div>

      {notifications.length > 0 && (
        <div className="mt-3 pt-3 border-t border-dashboard-border text-center">
          <a
            href="/notifications"
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            View All Notifications
          </a>
        </div>
      )}
    </Card>
  );
}
