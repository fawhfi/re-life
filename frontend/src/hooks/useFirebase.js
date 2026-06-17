// ============================================================================
// Firebase 初始化 Hook
// ============================================================================

import { useEffect, useState } from 'react';
import { initFirebase } from '../utils/firebase';

/**
 * Firebase 初始化 Hook
 * @returns {Object} 初始化状态
 */
export function useFirebase() {
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const config = {
      apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
      authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
      storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
      messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
      appId: import.meta.env.VITE_FIREBASE_APP_ID,
      databaseURL: import.meta.env.VITE_FIREBASE_DATABASE_URL,
    };

    try {
      initFirebase(config);
      setInitialized(true);
    } catch (err) {
      console.error('[Firebase] Initialization failed:', err);
      setError(err.message);
    }
  }, []);

  return { initialized, error };
}
