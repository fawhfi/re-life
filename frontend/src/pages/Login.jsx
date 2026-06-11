import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const { updateState } = useApp();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!username || !password) { setError('Please fill all fields'); return; }

    const FB = window.FB;
    if (!FB) { setError('Firebase not ready'); return; }

    try {
      if (isRegister) {
        await FB.register(username, password);
      }
      const user = await FB.login(username, password);
      localStorage.setItem('RE_LIFE_CURRENT_USER', user.displayName);
      updateState({ currentUser: user.displayName, userAvatar: user.photoUrl || '👤', userId: user.id, userKey: user._key });
      navigate('/');
    } catch (err) {
      setError(err.message || 'Login failed');
    }
  };

  return (
    <div className="login-page" style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--color-bg)', fontFamily: 'DM Sans, sans-serif'
    }}>
      <form onSubmit={handleSubmit} className="login-card" style={{
        background: 'var(--color-white)', borderRadius: 20, padding: 32,
        width: 340, boxShadow: '0 4px 24px rgba(0,0,0,0.06)'
      }}>
        <h2 style={{ margin: '0 0 4px', fontWeight: 900 }}>Re-Life</h2>
        <p style={{ margin: '0 0 20px', fontSize: 13, color: 'var(--color-gray-400)' }}>Green Living Assistant</p>

        <input className="login-input" placeholder="Username" value={username}
               onChange={e => setUsername(e.target.value)}
               style={{ width: '100%', padding: '12px', borderRadius: 10, border: '1px solid var(--color-gray-200)', marginBottom: 10, boxSizing: 'border-box' }} />

        <input className="login-input" type="password" placeholder="Password" value={password}
               onChange={e => setPassword(e.target.value)}
               style={{ width: '100%', padding: '12px', borderRadius: 10, border: '1px solid var(--color-gray-200)', marginBottom: 10, boxSizing: 'border-box' }} />

        {error && <div style={{ color: 'var(--color-red-500)', fontSize: 12, marginBottom: 10 }}>{error}</div>}

        <button type="submit" className="btn btn--primary" style={{ width: '100%', marginBottom: 8 }}>
          {isRegister ? 'Create Account' : 'Log In'}
        </button>

        <button type="button" className="btn btn--outline" style={{ width: '100%' }}
                onClick={() => { setIsRegister(!isRegister); setError(''); }}>
          {isRegister ? '← Back to Login' : 'Create Account'}
        </button>
      </form>
    </div>
  );
}
