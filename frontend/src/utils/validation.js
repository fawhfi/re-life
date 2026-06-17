// ============================================================================
// 表单验证工具
// ============================================================================

/**
 * 验证邮箱格式
 * @param {string} email - 邮箱地址
 * @returns {boolean} 是否有效
 */
export function validateEmail(email) {
  if (!email || typeof email !== 'string') return false;
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email.toLowerCase());
}

/**
 * 验证密码强度
 * @param {string} password - 密码
 * @returns {Object} 验证结果 {valid, errors}
 */
export function validatePassword(password) {
  const errors = [];

  if (!password || password.length < 8) {
    errors.push('Password must be at least 8 characters');
  }

  if (password && !/[A-Z]/.test(password)) {
    errors.push('Password must contain at least one uppercase letter');
  }

  if (password && !/[a-z]/.test(password)) {
    errors.push('Password must contain at least one lowercase letter');
  }

  if (password && !/[0-9]/.test(password)) {
    errors.push('Password must contain at least one number');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证用户名
 * @param {string} username - 用户名
 * @returns {Object} 验证结果
 */
export function validateUsername(username) {
  const errors = [];

  if (!username || username.length < 3) {
    errors.push('Username must be at least 3 characters');
  }

  if (username && username.length > 20) {
    errors.push('Username must be less than 20 characters');
  }

  if (username && !/^[a-zA-Z0-9_-]+$/.test(username)) {
    errors.push('Username can only contain letters, numbers, hyphens, and underscores');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * 验证验证码格式
 * @param {string} code - 验证码
 * @returns {boolean} 是否有效
 */
export function validateVerificationCode(code) {
  return /^\d{6}$/.test(code);
}

/**
 * 验证图像文件
 * @param {File} file - 文件对象
 * @returns {Object} 验证结果
 */
export function validateImageFile(file) {
  const errors = [];
  const maxSize = 10 * 1024 * 1024; // 10MB
  const allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];

  if (!file) {
    errors.push('No file selected');
    return { valid: false, errors };
  }

  if (!allowedTypes.includes(file.type)) {
    errors.push('Only JPEG, PNG, and WebP images are allowed');
  }

  if (file.size > maxSize) {
    errors.push('File size must be less than 10MB');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}
