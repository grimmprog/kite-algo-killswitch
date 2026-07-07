import { useState, useEffect, useCallback } from 'react';
import { DashboardLayout } from '../components/dashboard/DashboardLayout';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { get } from '../api/client';

interface Order {
  id: number;
  broker_order_id: string;
  symbol: string;
  exchange: string;
  quantity: number;
  price: number;
  side: string;
  status: 'PENDING' | 'COMPLETE' | 'REJECTED' | 'CANCELLED';
  error_message?: string;
  timestamp: string;
}

interface PaginatedResponse {
  orders: Order[];
  total: number;
  page: number;
  page_size: number;
}

type StatusFilter = 'ALL' | 'PENDING' | 'COMPLETE' | 'REJECTED' | 'CANCELLED';

const STATUS_COLORS: Record<string, string> = {
  COMPLETE: 'text-profit bg-profit/10 border-profit/30',
  PENDING: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  REJECTED: 'text-loss bg-loss/10 border-loss/30',
  CANCELLED: 'text-dashboard-muted bg-dashboard-bg border-dashboard-border',
};

export function TradeHistoryPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const totalPages = Math.ceil(total / pageSize);

  const fetchOrders = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> = {
        page,
        page_size: pageSize,
      };

      if (statusFilter !== 'ALL') {
        params.status = statusFilter;
      }
      if (dateFrom) {
        params.date_from = dateFrom;
      }
      if (dateTo) {
        params.date_to = dateTo;
      }

      const data = await get<PaginatedResponse>('/api/v1/trades/history', params);
      setOrders(data.orders || []);
      setTotal(data.total || 0);
      setError(null);
    } catch {
      setError('Failed to load order history.');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, statusFilter, dateFrom, dateTo]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, dateFrom, dateTo]);

  const formatTimestamp = (ts: string): string => {
    const date = new Date(ts);
    return date.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <DashboardLayout>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-dashboard-text">Order History</h1>
            <p className="text-sm text-dashboard-muted">
              {total} total order{total !== 1 ? 's' : ''}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={fetchOrders}>
            Refresh
          </Button>
        </div>

        {/* Filters */}
        <Card padding="sm">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="status-filter" className="block text-xs text-dashboard-muted mb-1">
                Status
              </label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ALL">All</option>
                <option value="PENDING">Pending</option>
                <option value="COMPLETE">Complete</option>
                <option value="REJECTED">Rejected</option>
                <option value="CANCELLED">Cancelled</option>
              </select>
            </div>
            <div>
              <label htmlFor="date-from" className="block text-xs text-dashboard-muted mb-1">
                From
              </label>
              <input
                id="date-from"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="date-to" className="block text-xs text-dashboard-muted mb-1">
                To
              </label>
              <input
                id="date-to"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="bg-dashboard-bg border border-dashboard-border rounded-lg px-2 py-1.5 text-sm text-dashboard-text focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {(statusFilter !== 'ALL' || dateFrom || dateTo) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStatusFilter('ALL');
                  setDateFrom('');
                  setDateTo('');
                }}
              >
                Clear Filters
              </Button>
            )}
          </div>
        </Card>

        {/* Error */}
        {error && (
          <div className="bg-loss/10 border border-loss/30 rounded-lg p-3 text-sm text-loss" role="alert">
            {error}
          </div>
        )}

        {/* Table */}
        <Card padding="none">
          {loading ? (
            <div className="p-8 text-center text-dashboard-muted">Loading orders...</div>
          ) : orders.length === 0 ? (
            <div className="p-8 text-center text-dashboard-muted">No orders found</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" role="table">
                <thead>
                  <tr className="border-b border-dashboard-border text-left">
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Symbol</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Exchange</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Qty</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Side</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted text-right">Price</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Status</th>
                    <th className="px-4 py-3 text-xs font-medium text-dashboard-muted">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr
                      key={order.id}
                      className="border-b border-dashboard-border/50 hover:bg-dashboard-bg/50"
                    >
                      <td className="px-4 py-3 font-medium text-dashboard-text">{order.symbol}</td>
                      <td className="px-4 py-3 text-dashboard-muted">{order.exchange}</td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        {order.quantity}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`font-medium ${order.side === 'BUY' ? 'text-profit' : 'text-loss'}`}
                        >
                          {order.side}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-dashboard-text">
                        {order.price > 0 ? `₹${order.price.toFixed(2)}` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block px-2 py-0.5 text-xs font-medium rounded border ${STATUS_COLORS[order.status] || 'text-dashboard-muted'}`}
                        >
                          {order.status}
                        </span>
                        {order.error_message && (
                          <p className="text-xs text-loss mt-0.5">{order.error_message}</p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-dashboard-muted whitespace-nowrap">
                        {formatTimestamp(order.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-dashboard-muted">
              Page {page} of {totalPages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
