// ============================================================================
// 认证状态管理
// ============================================================================

import { create } from 'zustand';
import { storage } from '../utils/storage';
import { getUserByName } from '../utils/firebase';

export const useAuthStore = create((set, get) => ({
  // 状态
  user: storage.get('CURRENT_USER'),
  isAuthenticated: !!storage.get('CURRENT_USER'),
  loading: false,
  error: null,

  // 登录
  login: async (displayName, password) => {
    set({ loading: true, error: null });
    try {
      // 这里应该调用 Firebase 认证逻辑
      // 简化版：从 Firebase DB 获取用户
      const user = await getUserByName(displayName);
      if (!user) {
        throw new Error('User not found');
      }

      const userData = {
        id: user.id,
        displayName: user.displayName,
        email: user.email,
        photoUrl: user.photoUrl,
        _key: user._key,
      };

      storage.set('CURRENT_USER', userData);
      set({ user: userData, isAuthenticated: true, loading: false });
      return userData;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  // 注册
  register: async (displayName, email, password) => {
    set({ loading: true, error: null });
    try {
      // 注册逻辑由后端 Firebase 处理
      // 这里只保存本地状态
      const userData = { displayName, email };
      storage.set('CURRENT_USER', userData);
      set({ user: userData, isAuthenticated: true, loading: false });
      return userData;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  // 登出
  logout: () => {
    storage.remove('CURRENT_USER');
    set({ user: null, isAuthenticated: false, error: null });
  },

  // 更新用户信息
  updateUser: (userData) => {
    const currentUser = get().user;
    const updatedUser = { ...currentUser, ...userData };
    storage.set('CURRENT_USER', updatedUser);
    set({ user: updatedUser });
  },

  // 清除错误
  clearError: () => set({ error: null }),
}));
