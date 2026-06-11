import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [state, setState] = useState({
    activeTab: 'home',
    scanMode: 'dispose',
    currentUser: null,
    userAvatar: '👤',
    userId: null,
    userKey: null,
    lang: localStorage.getItem('RE_LIFE_LANG') || 'en',
    debugMode: false,
    earnedPoints: 0,
    spentPoints: 0,
    claimedCoupons: [],
    records: [],
    tips: [],
    rewards: [],
    lastScanResult: null,
  });

  const updateState = useCallback((updates) => {
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  return (
    <AppContext.Provider value={{ state, updateState }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be inside AppProvider');
  return ctx;
}
