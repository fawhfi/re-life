// ============================================================================
// 认证 API
// ============================================================================

import apiClient from './client';

/**
 * 发送邮箱验证码
 * @param {string} email - 邮箱地址
 * @returns {Promise<Object>} 响应数据
 */
export async function sendVerificationCode(email) {
  const response = await apiClient.post('/send-verification', { email });
  return response.data;
}

/**
 * 验证邮箱验证码
 * @param {string} email - 邮箱地址
 * @param {string} code - 验证码
 * @returns {Promise<Object>} 响应数据
 */
export async function verifyCode(email, code) {
  const response = await apiClient.post('/verify-code', { email, code });
  return response.data;
}

/**
 * 发送密码重置验证码
 * @param {string} email - 邮箱地址
 * @returns {Promise<Object>} 响应数据
 */
export async function forgotPassword(email) {
  const response = await apiClient.post('/forgot-password', { email });
  return response.data;
}

/**
 * 重置密码
 * @param {string} email - 邮箱地址
 * @param {string} code - 验证码
 * @param {string} password - 新密码
 * @returns {Promise<Object>} 响应数据
 */
export async function resetPassword(email, code, password) {
  const response = await apiClient.post('/reset-password', {
    email,
    code,
    password,
  });
  return response.data;
}
