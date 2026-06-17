// ============================================================================
// 本地存储工具（安全包装 localStorage）
// ============================================================================

const STORAGE_PREFIX = 'RE_LIFE_';

/**
 * 安全的 localStorage 包装器
 */
export const storage = {
  /**
   * 获取存储值
   * @param {string} key - 键名
   * @param {any} defaultValue - 默认值
   * @returns {any} 存储的值或默认值
   */
  get(key, defaultValue = null) {
    try {
      const item = localStorage.getItem(STORAGE_PREFIX + key);
      if (item === null) return defaultValue;
      return JSON.parse(item);
    } catch (error) {
      console.warn('[Storage] Failed to get:', key, error);
      return defaultValue;
    }
  },

  /**
   * 设置存储值
   * @param {string} key - 键名
   * @param {any} value - 要存储的值
   */
  set(key, value) {
    try {
      localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
    } catch (error) {
      console.warn('[Storage] Failed to set:', key, error);
    }
  },

  /**
   * 删除存储值
   * @param {string} key - 键名
   */
  remove(key) {
    try {
      localStorage.removeItem(STORAGE_PREFIX + key);
    } catch (error) {
      console.warn('[Storage] Failed to remove:', key, error);
    }
  },

  /**
   * 清空所有存储
   */
  clear() {
    try {
      Object.keys(localStorage).forEach(key => {
        if (key.startsWith(STORAGE_PREFIX)) {
          localStorage.removeItem(key);
        }
      });
    } catch (error) {
      console.warn('[Storage] Failed to clear:', error);
    }
  }
};
