import { useApp } from '../context/AppContext';
import { useNavigate } from 'react-router-dom';

const THEMES = ['light', 'dark', 'forest', 'ocean', 'sunset', 'midnight'];

export default function Settings() {
  const { state, updateState } = useApp();
  const navigate = useNavigate();

  const setTheme = (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('RE_LIFE_THEME', theme);
  };

  const toggleLang = () => {
    const lang = state.lang === 'en' ? 'zh' : 'en';
    localStorage.setItem('RE_LIFE_LANG', lang);
    updateState({ lang });
  };

  const logout = () => {
    localStorage.removeItem('RE_LIFE_CURRENT_USER');
    updateState({ currentUser: null });
    navigate('/login');
  };

  return (
    <section className="tab active" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="card">
        <h3 style={{ margin: '0 0 12px' }}>Settings</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>🎨 Theme</span>
            <select value={localStorage.getItem('RE_LIFE_THEME') || 'light'} onChange={e => setTheme(e.target.value)}
                    style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid var(--color-gray-200)' }}>
              {THEMES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <button className="btn btn--outline" onClick={toggleLang}>
            🌐 Language: {state.lang === 'en' ? 'English' : '中文'}
          </button>
          {state.currentUser && (
            <button className="btn btn--danger" onClick={logout}>Logout</button>
          )}
        </div>
      </div>
    </section>
  );
}
