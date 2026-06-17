// ============================================================================
// 登录页面
// ============================================================================

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { validateEmail, validateVerificationCode } from '../utils/validation';
import { sendVerificationCode, verifyCode } from '../api/auth';
import Button from '../components/common/Button';
import './LoginPage.css';

export default function LoginPage() {
  const { login, loading } = useAuth();
  const [step, setStep] = useState('email'); // 'email' | 'code'
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [devCode, setDevCode] = useState('');

  const handleSendCode = async (e) => {
    e.preventDefault();
    setError('');

    if (!validateEmail(email)) {
      setError('Invalid email address');
      return;
    }

    try {
      const result = await sendVerificationCode(email);
      if (result.dev_code) {
        setDevCode(result.dev_code);
      }
      setStep('code');
    } catch (err) {
      setError(err.message || 'Failed to send verification code');
    }
  };

  const handleVerifyCode = async (e) => {
    e.preventDefault();
    setError('');

    if (!validateVerificationCode(code)) {
      setError('Invalid verification code');
      return;
    }

    try {
      await verifyCode(email, code);
      await login(email, code);
    } catch (err) {
      setError(err.message || 'Verification failed');
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>Re-Life</h1>
          <p>Green Future Starts Here</p>
        </div>

        {step === 'email' ? (
          <form onSubmit={handleSendCode} className="login-form">
            <input
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-field"
              required
            />

            {error && <div className="error-message">{error}</div>}

            <Button
              type="submit"
              fullWidth
              loading={loading}
            >
              Send Verification Code
            </Button>

            <div className="login-footer">
              <span>Don't have an account?</span>
              <Link to="/register">Register</Link>
            </div>
          </form>
        ) : (
          <form onSubmit={handleVerifyCode} className="login-form">
            <p className="info-text">
              Verification code sent to <strong>{email}</strong>
            </p>

            {devCode && (
              <div className="dev-code">
                Dev Code: <strong>{devCode}</strong>
              </div>
            )}

            <input
              type="text"
              placeholder="Enter 6-digit code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="input-field"
              maxLength={6}
              required
            />

            {error && <div className="error-message">{error}</div>}

            <Button
              type="submit"
              fullWidth
              loading={loading}
            >
              Verify & Login
            </Button>

            <Button
              type="button"
              variant="outline"
              fullWidth
              onClick={() => setStep('email')}
            >
              Back
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
