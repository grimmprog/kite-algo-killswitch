import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { apiClient } from '../api/client';

interface User {
  id: number;
  email: string;
  capital: number;
  riskProfile: string;
  dailyLossLimitPercent: number;
  maxTradeRiskPercent: number;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = 'kite_algo_token';
const USER_KEY = 'kite_algo_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    const storedUser = localStorage.getItem(USER_KEY);

    return {
      token: storedToken,
      user: storedUser ? JSON.parse(storedUser) : null,
      isAuthenticated: !!storedToken,
      isLoading: false,
    };
  });

  const login = useCallback(async (email: string, password: string) => {
    setState((prev) => ({ ...prev, isLoading: true }));

    try {
      const response = await apiClient.post('/api/v1/auth/login', { email, password });
      const { access_token, user_id } = response.data;

      localStorage.setItem(TOKEN_KEY, access_token);

      const user: User = {
        id: user_id,
        email,
        capital: response.data.capital ?? 100000,
        riskProfile: response.data.risk_profile ?? 'moderate',
        dailyLossLimitPercent: response.data.daily_loss_limit_percent ?? 2.0,
        maxTradeRiskPercent: response.data.max_trade_risk_percent ?? 1.0,
      };

      localStorage.setItem(USER_KEY, JSON.stringify(user));

      setState({
        token: access_token,
        user,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch (error) {
      setState((prev) => ({ ...prev, isLoading: false }));
      throw error;
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);

    setState({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      const response = await apiClient.post('/api/v1/auth/refresh');
      const { access_token } = response.data;

      localStorage.setItem(TOKEN_KEY, access_token);
      setState((prev) => ({ ...prev, token: access_token }));
    } catch {
      logout();
    }
  }, [logout]);

  // Check token validity on mount
  useEffect(() => {
    if (state.token) {
      // Attempt to validate token by checking expiry
      try {
        const payload = JSON.parse(atob(state.token.split('.')[1]));
        const expiresAt = payload.exp * 1000;

        if (Date.now() >= expiresAt) {
          logout();
        }
      } catch {
        // Invalid token format, logout
        logout();
      }
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refreshToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
