// ============================================================================
// UI 状态管理
// ============================================================================

import { create } from 'zustand';
import { storage } from '../utils/storage';

export const useUIStore = create((set) => ({
  // 主题
  theme: storage.get('THEME', 'light'),

  // 语言
  language: storage.get('LANG', 'en'),

  // 声音
  soundEnabled: storage.get('SOUND_ENABLED', true),

  // 调试模式
  debugMode: storage.get('DEBUG_MODE', false),

  // 模态框
  modalOpen: false,
  modalContent: null,

  // Toast 通知
  toastOpen: false,
  toastMessage: '',
  toastType: 'info', // 'info' | 'success' | 'error' | 'warning'

  // 设置主题
  setTheme: (theme) => {
    storage.set('THEME', theme);
    document.documentElement.setAttribute('data-theme', theme);
    set({ theme });
  },

  // 设置语言
  setLanguage: (language) => {
    storage.set('LANG', language);
    document.documentElement.lang = language === 'zh' ? 'zh-HK' : 'en';
    set({ language });
  },

  // 切换声音
  toggleSound: () => set((state) => {
    const soundEnabled = !state.soundEnabled;
    storage.set('SOUND_ENABLED', soundEnabled);
    return { soundEnabled };
  }),

  // 切换调试模式
  toggleDebug: () => set((state) => {
    const debugMode = !state.debugMode;
    storage.set('DEBUG_MODE', debugMode);
    return { debugMode };
  }),

  // 打开模态框
  openModal: (content) => set({ modalOpen: true, modalContent: content }),

  // 关闭模态框
  closeModal: () => set({ modalOpen: false, modalContent: null }),

  // 显示 Toast
  showToast: (message, type = 'info') => {
    set({ toastOpen: true, toastMessage: message, toastType: type });
    // 3 秒后自动关闭
    setTimeout(() => {
      set({ toastOpen: false });
    }, 3000);
  },

  // 关闭 Toast
  closeToast: () => set({ toastOpen: false }),
}));
