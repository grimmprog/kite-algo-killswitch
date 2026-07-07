import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';

interface FormData {
  email: string;
  password: string;
  confirmPassword: string;
  capital: string;
  riskProfile: string;
}

interface FormErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
  capital?: string;
  riskProfile?: string;
  form?: string;
}

const RISK_PROFILES = [
  { value: 'conservative', label: 'Conservative' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'aggressive', label: 'Aggressive' },
];

export function RegisterPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);

  const [form, setForm] = useState<FormData>({
    email: '',
    password: '',
    confirmPassword: '',
    capital: '',
    riskProfile: 'moderate',
  });

  const [errors, setErrors] = useState<FormErrors>({});

  function updateField(field: keyof FormData, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function validate(): boolean {
    const newErrors: FormErrors = {};

    if (!form.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      newErrors.email = 'Enter a valid email address';
    }

    if (!form.password) {
      newErrors.password = 'Password is required';
    } else if (form.password.length < 8) {
      newErrors.password = 'Password must be at least 8 characters';
    }

    if (!form.confirmPassword) {
      newErrors.confirmPassword = 'Please confirm your password';
    } else if (form.password !== form.confirmPassword) {
      newErrors.confirmPassword = 'Passwords do not match';
    }

    if (!form.capital.trim()) {
      newErrors.capital = 'Trading capital is required';
    } else {
      const capitalNum = parseFloat(form.capital);
      if (isNaN(capitalNum) || capitalNum <= 0) {
        newErrors.capital = 'Enter a valid positive amount';
      }
    }

    if (!form.riskProfile) {
      newErrors.riskProfile = 'Select a risk profile';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setErrors({});

    if (!validate()) return;

    setIsLoading(true);

    try {
      await apiClient.post('/api/v1/auth/register', {
        email: form.email,
        password: form.password,
        capital: parseFloat(form.capital),
        risk_profile: form.riskProfile,
      });

      navigate('/login', { replace: true });
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Registration failed. Please try again.';
      setErrors({ form: message });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-dashboard-bg px-4 py-8">
      <div className="w-full max-w-md">
        <div className="bg-dashboard-card border border-dashboard-border rounded-xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-dashboard-text">Create Account</h1>
            <p className="text-sm text-dashboard-muted mt-1">
              Start trading with risk management
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
              value={form.email}
              onChange={(e) => updateField('email', e.target.value)}
              error={errors.email}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />

            <Input
              label="Password"
              type="password"
              value={form.password}
              onChange={(e) => updateField('password', e.target.value)}
              error={errors.password}
              placeholder="Min. 8 characters"
              autoComplete="new-password"
              required
            />

            <Input
              label="Confirm Password"
              type="password"
              value={form.confirmPassword}
              onChange={(e) => updateField('confirmPassword', e.target.value)}
              error={errors.confirmPassword}
              placeholder="Re-enter password"
              autoComplete="new-password"
              required
            />

            <Input
              label="Trading Capital (₹)"
              type="number"
              value={form.capital}
              onChange={(e) => updateField('capital', e.target.value)}
              error={errors.capital}
              placeholder="100000"
              min="1"
              step="1"
              required
            />

            <div className="w-full">
              <label
                htmlFor="risk-profile"
                className="block text-sm font-medium text-dashboard-text mb-1.5"
              >
                Risk Profile
              </label>
              <select
                id="risk-profile"
                value={form.riskProfile}
                onChange={(e) => updateField('riskProfile', e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-dashboard-bg border border-dashboard-border text-dashboard-text text-sm font-mono transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                aria-invalid={!!errors.riskProfile}
              >
                {RISK_PROFILES.map((profile) => (
                  <option key={profile.value} value={profile.value}>
                    {profile.label}
                  </option>
                ))}
              </select>
              {errors.riskProfile && (
                <p className="mt-1 text-xs text-loss" role="alert">
                  {errors.riskProfile}
                </p>
              )}
            </div>

            <Button
              type="submit"
              isLoading={isLoading}
              className="w-full"
              size="lg"
            >
              Create Account
            </Button>
          </form>

          <p className="text-center text-sm text-dashboard-muted mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-blue-500 hover:text-blue-400 font-medium">
              Sign In
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
