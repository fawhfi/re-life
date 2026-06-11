import { useApp } from '../context/AppContext';
import { useNavigate } from 'react-router-dom';

export default function Header() {
  const { state } = useApp();
  const navigate = useNavigate();

  const avatar = state.userAvatar;
  const isImage = avatar && avatar.startsWith('data:');

  return (
    <header className="app-header">
      <div className="header-left">
        <div className="header-avatar" onClick={() => state.currentUser ? null : navigate('/login')}>
          {isImage ? (
            <img src={avatar} style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }}
                 onError={e => e.target.parentElement.textContent = '👤'} />
          ) : (
            avatar || '👤'
          )}
        </div>
        <span className="header-title">Re-Life</span>
        <span className="header-user">{state.currentUser || 'Not Logged In'}</span>
      </div>
      <span className="header-time">{new Date().toLocaleTimeString()}</span>
    </header>
  );
}
