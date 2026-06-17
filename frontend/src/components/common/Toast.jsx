// ============================================================================
// Toast 通知组件
// ============================================================================

import { useEffect } from 'react';
import { useUIStore } from '../../store/uiStore';
import './Toast.css';

export default function Toast() {
  const { toastOpen, toastMessage, toastType, closeToast } = useUIStore();

  useEffect(() => {
    if (toastOpen) {
      const timer = setTimeout(() => {
        closeToast();
      }, 3000);

      return () => clearTimeout(timer);
    }
  }, [toastOpen, closeToast]);

  if (!toastOpen) return null;

  const icons = {
    info: 'ℹ️',
    success: '✅',
    error: '❌',
    warning: '⚠️',
  };

  return (
    <div className={`toast toast--${toastType}`}>
      <span className="toast-icon">{icons[toastType]}</span>
      <span className="toast-message">{toastMessage}</span>
      <button className="toast-close" onClick={closeToast}>×</button>
    </div>
  );
}
