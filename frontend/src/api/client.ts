import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const TOKEN_KEY = 'kite_algo_token';

/**
 * Axios instance configured for the trading platform API.
 * - Attaches JWT token from localStorage to every request
 * - Handles 401 responses by redirecting to login
 * - Provides global error handling
 */
export const apiClient = axios.create({
  baseURL: '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach JWT token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: handle errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      const { status } = error.response;

      switch (status) {
        case 401:
          // Token expired or invalid - clear auth state and redirect to login
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem('kite_algo_user');

          // Only redirect if not already on login page
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          break;

        case 403:
          console.error('Access denied: insufficient permissions');
          break;

        case 429:
          console.error('Rate limit exceeded. Please wait before retrying.');
          break;

        case 500:
          console.error('Server error. Please try again later.');
          break;

        default:
          break;
      }
    } else if (error.request) {
      // Network error - no response received
      console.error('Network error: unable to reach the server');
    }

    return Promise.reject(error);
  }
);

// Convenience methods with typed responses
export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const response = await apiClient.get<T>(url, { params });
  return response.data;
}

export async function post<T>(url: string, data?: unknown): Promise<T> {
  const response = await apiClient.post<T>(url, data);
  return response.data;
}

export async function put<T>(url: string, data?: unknown): Promise<T> {
  const response = await apiClient.put<T>(url, data);
  return response.data;
}

export async function del<T>(url: string): Promise<T> {
  const response = await apiClient.delete<T>(url);
  return response.data;
}
