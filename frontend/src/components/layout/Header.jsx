// ============================================================================
// 头部组件
// ============================================================================

import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import './Header.css';

export default function Header() {
  const { user, isAuthenticated } = useAuthStore();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const formatTime = (date) => {
    return new Intl.DateTimeFormat('en-HK', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date);
  };

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="header-avatar">
          {isAuthenticated ? (user?.photoUrl || '👤') : '👤'}
        </div>
        <span className="header-title">Re-Life</span>
        <span className="header-user">
          {isAuthenticated ? user?.displayName : 'Not Logged In'}
        </span>
      </div>
      <span className="header-time">{formatTime(time)}</span>
    </header>
  );
}
