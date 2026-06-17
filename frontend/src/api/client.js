// ============================================================================
// Axios HTTP 客户端配置
// ============================================================================

import axios from 'axios';
import { storage } from '../utils/storage';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * 创建 Axios 实例
 */
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 请求拦截器
 */
apiClient.interceptors.request.use(
  (config) => {
    // 添加认证 token（如果存在）
    const user = storage.get('CURRENT_USER');
    if (user && user.token) {
      config.headers.Authorization = `Bearer ${user.token}`;
    }

    // 日志
    console.log('[API] Request:', config.method?.toUpperCase(), config.url);

    return config;
  },
  (error) => {
    console.error('[API] Request error:', error);
    return Promise.reject(error);
  }
);

/**
 * 响应拦截器
 */
apiClient.interceptors.response.use(
  (response) => {
    console.log('[API] Response:', response.status, response.config.url);
    return response;
  },
  (error) => {
    // 处理错误
    const status = error.response?.status;
    const message = error.response?.data?.error || error.message;

    console.error('[API] Response error:', status, message);

    // 429 - 速率限制
    if (status === 429) {
      return Promise.reject({
        message: 'Too many requests. Please slow down.',
        status: 429,
      });
    }

    // 401 - 未授权
    if (status === 401) {
      // 清除认证信息
      storage.remove('CURRENT_USER');
      // 可以触发跳转到登录页
      return Promise.reject({
        message: 'Session expired. Please login again.',
        status: 401,
      });
    }

    // 500 - 服务器错误
    if (status >= 500) {
      return Promise.reject({
        message: 'Server error. Please try again later.',
        status,
      });
    }

    return Promise.reject({
      message,
      status,
    });
  }
);

export default apiClient;
