import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';

export function LoginPage() {
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string; form?: string }>({});

  function validate(): boolean {
    const newErrors: typeof errors = {};

    if (!email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      newErrors.email = 'Enter a valid email address';
    }

    if (!password) {
      newErrors.password = 'Password is required';
    } else if (password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErrors({});

    if (!validate()) return;

    try {
      await login(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Login failed. Please check your credentials.';
      setErrors({ form: message });
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-dashboard-bg px-4">
      <div className="w-full max-w-md">
        <div className="bg-dashboard-card border border-dashboard-border rounded-xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-dashboard-text">Sign In</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              Access your trading dashboard
            </p>
          </div>

          {errors.form && (
            <div
              className="mb-4 p-3 rounded-lg bg-loss/10 border border-loss/20 text-loss text-sm"
              role="alert"
            >
              {errors.form}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={errors.email}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />

            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={errors.password}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />

            <Button
              type="submit"
              isLoading={isLoading}
              className="w-full"
              size="lg"
            >
              Sign In
            </Button>
          </form>

          <p className="text-center text-sm text-dashboard-muted mt-6">
            Don&apos;t have an account?{' '}
            <Link to="/register" className="text-blue-500 hover:text-blue-400 font-medium">
              Register
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
