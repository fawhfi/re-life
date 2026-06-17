// ============================================================================
// 注册页面
// ============================================================================

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { validateEmail, validateUsername, validatePassword, validateVerificationCode } from '../utils/validation';
import { sendVerificationCode, verifyCode } from '../api/auth';
import Button from '../components/common/Button';
import './RegisterPage.css';

export default function RegisterPage() {
  const { register, loading } = useAuth();
  const [step, setStep] = useState('email'); // 'email' | 'code' | 'profile'
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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
      setStep('profile');
    } catch (err) {
      setError(err.message || 'Verification failed');
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError('');

    // 验证用户名
    const usernameValidation = validateUsername(username);
    if (!usernameValidation.valid) {
      setError(usernameValidation.errors[0]);
      return;
    }

    // 验证密码
    const passwordValidation = validatePassword(password);
    if (!passwordValidation.valid) {
      setError(passwordValidation.errors[0]);
      return;
    }

    // 确认密码匹配
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    try {
      await register(username, email, password);
    } catch (err) {
      setError(err.message || 'Registration failed');
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>Re-Life</h1>
          <p>Create Your Account</p>
        </div>

        {step === 'email' && (
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

            <Button type="submit" fullWidth loading={loading}>
              Send Verification Code
            </Button>

            <div className="login-footer">
              <span>Already have an account?</span>
              <Link to="/login">Login</Link>
            </div>
          </form>
        )}

        {step === 'code' && (
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

            <Button type="submit" fullWidth loading={loading}>
              Verify Code
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

        {step === 'profile' && (
          <form onSubmit={handleRegister} className="login-form">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input-field"
              required
            />

            <input
              type="password"
              placeholder="Password (min 8 characters)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-field"
              required
            />

            <input
              type="password"
              placeholder="Confirm Password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="input-field"
              required
            />

            {error && <div className="error-message">{error}</div>}

            <Button type="submit" fullWidth loading={loading}>
              Complete Registration
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
