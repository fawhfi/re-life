// ============================================================================
// 设置页面
// ============================================================================

import { useUIStore } from '../store/uiStore';
import { useAuth } from '../hooks/useAuth';
import Button from '../components/common/Button';
import './SettingsPage.css';

export default function SettingsPage() {
  const {
    theme,
    language,
    soundEnabled,
    debugMode,
    setTheme,
    setLanguage,
    toggleSound,
    toggleDebug,
  } = useUIStore();

  const { user, isAuthenticated, logout } = useAuth();

  const themes = [
    { value: 'light', label: '🌿 Light' },
    { value: 'dark', label: '🌙 Dark' },
    { value: 'forest', label: '🌲 Forest' },
    { value: 'ocean', label: '🌊 Ocean' },
    { value: 'sunset', label: '🌅 Sunset' },
    { value: 'midnight', label: '✨ Midnight' },
  ];

  const handleLanguageToggle = () => {
    setLanguage(language === 'en' ? 'zh' : 'en');
  };

  return (
    <section className="tab active">
      <div className="more-section">
        <div className="card">
          <h3 className="section-title mb-3">Settings</h3>
          <div className="flex-col gap-2">
            <div className="setting-row">
              <span className="setting-label">Theme</span>
              <select
                className="select-field"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
              >
                {themes.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <Button
              variant="outline"
              fullWidth
              onClick={toggleSound}
            >
              {soundEnabled ? '🔊' : '🔇'} Sound {soundEnabled ? 'ON' : 'OFF'}
            </Button>

            <Button
              variant="outline"
              fullWidth
              onClick={handleLanguageToggle}
            >
              🌐 Language: {language === 'en' ? 'English' : '中文'}
            </Button>

            <Button
              variant="outline"
              fullWidth
              onClick={toggleDebug}
            >
              🔧 Debug Mode: {debugMode ? 'ON' : 'OFF'}
            </Button>

            {isAuthenticated && (
              <Button
                variant="danger"
                fullWidth
                onClick={logout}
              >
                Logout ({user?.displayName})
              </Button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
