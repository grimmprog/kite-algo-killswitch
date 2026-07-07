import type { ReactNode } from 'react';
import { AuthProvider } from './AuthContext';
import { WebSocketProvider } from './WebSocketContext';

interface AppProviderProps {
  children: ReactNode;
}

/**
 * AppProvider wraps the application with all required context providers.
 * Order matters: AuthProvider must come first since WebSocketProvider depends on auth state.
 */
export function AppProvider({ children }: AppProviderProps) {
  return (
    <AuthProvider>
      <WebSocketProvider>{children}</WebSocketProvider>
    </AuthProvider>
  );
}
