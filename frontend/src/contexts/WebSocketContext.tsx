import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuth } from './AuthContext';

// --- Existing event types ---

interface RiskUpdate {
  pnl: number;
  netDelta: number;
  netGamma: number;
  netVega: number;
  marginUsed: number;
  updatedAt: string;
}

interface PositionUpdate {
  symbol: string;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
}

interface OrderUpdate {
  orderId: string;
  symbol: string;
  status: string;
  message: string;
}

interface KillSwitchUpdate {
  active: boolean;
  reason?: string;
  timestamp: string;
}

// --- New event types ---

export interface ScanSignalEvent {
  id: string;
  symbol: string;
  scanType: 'trend_pullback' | 'consolidation_breakout';
  confidenceScore: number;
  entryPrice: number;
  stopLoss: number;
  targetPrice: number;
  maxPotentialLoss: number;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface SignalExpiredEvent {
  id: string;
  symbol: string;
  expiredAt: string;
}

export interface ConsolidationUpdateEvent {
  symbol: string;
  rangeHigh: number;
  rangeLow: number;
  avgPrice: number;
  candleCount: number;
  durationMinutes: number;
  isBreakout: boolean;
  breakoutPrice?: number;
}

export interface PositionMonitorUpdateEvent {
  positionId: number;
  symbol: string;
  entryPrice: number;
  currentPrice: number;
  stopLoss: number;
  target: number;
  trailingStopEnabled: boolean;
  trailingStopLevel?: number;
  unrealizedPnl: number;
  distanceToSlPct: number;
  distanceToTargetPct: number;
  status: string;
}

export interface ExitConditionUpdateEvent {
  positionId: number;
  conditions: Array<{
    name: string;
    description: string;
    isMet: boolean;
    details?: string;
  }>;
}

export interface AutoExitTriggeredEvent {
  positionId: number;
  symbol: string;
  reason: string;
  exitPrice: number;
  pnl: number;
  timestamp: string;
}

export interface NotificationEvent {
  id: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  category: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface MonitorStatusEvent {
  isActive: boolean;
  currentPnl: number;
  nearestThreshold: number;
  distanceToThreshold: number;
  thresholdType: string;
}

export interface ThresholdWarningEvent {
  thresholdType: string;
  currentValue: number;
  thresholdValue: number;
  distancePct: number;
  message: string;
}

export interface AIAnalysisResultEvent {
  requestId: string;
  analysisType: string;
  result: Record<string, unknown>;
  timestamp: string;
}

export interface AIRiskWarningEvent {
  severity: 'info' | 'warning' | 'critical';
  message: string;
  category: string;
  requiresAcknowledgment: boolean;
}

export interface AIMarketUpdateEvent {
  sessionType: string;
  keyPoints: string[];
  bias: string;
  expectedRange: { low: number; high: number };
  keyLevels: { support: number[]; resistance: number[] };
  detailedAnalysis?: string;
}

export interface SignalPriceUpdateEvent {
  signalId: string;
  symbol: string;
  currentPrice: number;
  changeFromEntry: number;
  changePct: number;
  timestamp: string;
}

// --- Event listener type ---
type EventListener<T = unknown> = (data: T) => void;

// --- Context type ---

interface WebSocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  // Existing state
  riskMetrics: RiskUpdate | null;
  positions: PositionUpdate[];
  killSwitchStatus: KillSwitchUpdate | null;
  lastOrderUpdate: OrderUpdate | null;
  // Event subscription methods for new events
  on: <T = unknown>(event: string, listener: EventListener<T>) => void;
  off: <T = unknown>(event: string, listener: EventListener<T>) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const { token, isAuthenticated } = useAuth();
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [riskMetrics, setRiskMetrics] = useState<RiskUpdate | null>(null);
  const [positions, setPositions] = useState<PositionUpdate[]>([]);
  const [killSwitchStatus, setKillSwitchStatus] = useState<KillSwitchUpdate | null>(null);
  const [lastOrderUpdate, setLastOrderUpdate] = useState<OrderUpdate | null>(null);
  const socketRef = useRef<Socket | null>(null);

  const connect = useCallback(() => {
    if (!token) return null;

    const newSocket = io(window.location.origin, {
      auth: { token },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    });

    newSocket.on('connect', () => {
      setIsConnected(true);
    });

    newSocket.on('disconnect', () => {
      setIsConnected(false);
    });

    // Existing event handlers
    newSocket.on('risk_update', (data: RiskUpdate) => {
      setRiskMetrics(data);
    });

    newSocket.on('position_update', (data: PositionUpdate[]) => {
      setPositions(data);
    });

    newSocket.on('order_update', (data: OrderUpdate) => {
      setLastOrderUpdate(data);
    });

    newSocket.on('killswitch_update', (data: KillSwitchUpdate) => {
      setKillSwitchStatus(data);
    });

    newSocket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error.message);
    });

    return newSocket;
  }, [token]);

  useEffect(() => {
    if (isAuthenticated && token) {
      const newSocket = connect();
      if (newSocket) {
        setSocket(newSocket);
        socketRef.current = newSocket;
      }
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
        socketRef.current = null;
        setSocket(null);
        setIsConnected(false);
      }
    };
  }, [isAuthenticated, token]); // eslint-disable-line react-hooks/exhaustive-deps

  // Generic event subscription methods for new feature hooks
  const on = useCallback(<T = unknown>(event: string, listener: EventListener<T>) => {
    if (socketRef.current) {
      socketRef.current.on(event, listener as EventListener);
    }
  }, []);

  const off = useCallback(<T = unknown>(event: string, listener: EventListener<T>) => {
    if (socketRef.current) {
      socketRef.current.off(event, listener as EventListener);
    }
  }, []);

  return (
    <WebSocketContext.Provider
      value={{
        socket,
        isConnected,
        riskMetrics,
        positions,
        killSwitchStatus,
        lastOrderUpdate,
        on,
        off,
      }}
    >
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WebSocketContextType {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
}
