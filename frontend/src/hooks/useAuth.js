// ============================================================================
// 认证相关 Hook
// ============================================================================

import { useAuthStore } from '../store/authStore';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';

/**
 * 认证 Hook
 * @returns {Object} 认证相关状态和方法
 */
export function useAuth() {
  const navigate = useNavigate();
  const {
    user,
    isAuthenticated,
    loading,
    error,
    login,
    register,
    logout,
    updateUser,
    clearError,
  } = useAuthStore();

  // 登录包装器
  const handleLogin = useCallback(async (displayName, password) => {
    try {
      await login(displayName, password);
      navigate('/');
    } catch (error) {
      console.error('[Auth] Login failed:', error);
      throw error;
    }
  }, [login, navigate]);

  // 注册包装器
  const handleRegister = useCallback(async (displayName, email, password) => {
    try {
      await register(displayName, email, password);
      navigate('/');
    } catch (error) {
      console.error('[Auth] Register failed:', error);
      throw error;
    }
  }, [register, navigate]);

  // 登出包装器
  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  return {
    user,
    isAuthenticated,
    loading,
    error,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    updateUser,
    clearError,
  };
}
