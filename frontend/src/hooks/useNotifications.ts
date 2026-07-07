import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from '../contexts/WebSocketContext';
import type {
  NotificationEvent,
  MonitorStatusEvent,
  ThresholdWarningEvent,
} from '../contexts/WebSocketContext';
import { get, post } from '../api/client';

// --- Types ---

export type NotificationSeverity = 'info' | 'warning' | 'critical';

export interface Notification {
  id: string;
  severity: NotificationSeverity;
  title: string;
  message: string;
  category: string;
  timestamp: string;
  read: boolean;
  metadata?: Record<string, unknown>;
}

export interface MonitorStatus {
  isActive: boolean;
  currentPnl: number;
  nearestThreshold: number;
  distanceToThreshold: number;
  thresholdType: string;
}

export interface ThresholdWarning {
  thresholdType: string;
  currentValue: number;
  thresholdValue: number;
  distancePct: number;
  message: string;
}

const MAX_FEED_SIZE = 100;

interface UseNotificationsReturn {
  notifications: Notification[];
  unreadCount: number;
  monitorStatus: MonitorStatus | null;
  lastThresholdWarning: ThresholdWarning | null;
  isLoading: boolean;
  error: string | null;
  fetchNotifications: (offset?: number, limit?: number) => Promise<Notification[]>;
  markAsRead: (notificationId: string) => Promise<void>;
  markAllAsRead: () => void;
}

/**
 * Hook for real-time notification feed.
 * - Subscribes to notification, monitor_status, and threshold_warning WebSocket events
 * - Maintains a rolling feed of max 100 notifications
 * - Provides mark-as-read and fetch history actions
 */
export function useNotifications(): UseNotificationsReturn {
  const { on, off } = useWebSocket();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [monitorStatus, setMonitorStatus] = useState<MonitorStatus | null>(null);
  const [lastThresholdWarning, setLastThresholdWarning] = useState<ThresholdWarning | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Subscribe to WebSocket events
  useEffect(() => {
    const handleNotification = (data: NotificationEvent) => {
      const notification: Notification = {
        ...data,
        read: false,
      };
      setNotifications((prev) => {
        const updated = [notification, ...prev];
        // Retain max 100 in the feed
        return updated.slice(0, MAX_FEED_SIZE);
      });
    };

    const handleMonitorStatus = (data: MonitorStatusEvent) => {
      setMonitorStatus(data);
    };

    const handleThresholdWarning = (data: ThresholdWarningEvent) => {
      setLastThresholdWarning(data);
    };

    on<NotificationEvent>('notification', handleNotification);
    on<MonitorStatusEvent>('monitor_status', handleMonitorStatus);
    on<ThresholdWarningEvent>('threshold_warning', handleThresholdWarning);

    return () => {
      off<NotificationEvent>('notification', handleNotification);
      off<MonitorStatusEvent>('monitor_status', handleMonitorStatus);
      off<ThresholdWarningEvent>('threshold_warning', handleThresholdWarning);
    };
  }, [on, off]);

  const fetchNotifications = useCallback(async (offset = 0, limit = 50) => {
    try {
      setIsLoading(true);
      setError(null);
      const result = await get<Notification[]>('/api/v1/notifications', { offset, limit });
      if (offset === 0) {
        setNotifications(result.slice(0, MAX_FEED_SIZE));
      }
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch notifications';
      setError(message);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, []);

  const markAsRead = useCallback(async (notificationId: string) => {
    try {
      await post(`/api/v1/notifications/${notificationId}/read`);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notificationId ? { ...n, read: true } : n))
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to mark notification as read';
      setError(message);
    }
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, []);

  const unreadCount = notifications.filter((n) => !n.read).length;

  // Fetch initial notifications on mount
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  return {
    notifications,
    unreadCount,
    monitorStatus,
    lastThresholdWarning,
    isLoading,
    error,
    fetchNotifications,
    markAsRead,
    markAllAsRead,
  };
}
