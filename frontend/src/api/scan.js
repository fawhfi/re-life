// ============================================================================
// 扫描分析 API
// ============================================================================

import apiClient from './client';

/**
 * 扫描图像并进行 AI 分析
 * @param {File} file - 图像文件
 * @param {Object} options - 扫描选项
 * @param {string} options.mode - 模式: 'dispose' 或 'purchase'
 * @param {string} options.itemType - 物品类型: 'food' 或 'general'
 * @param {string} options.itemState - 状态: 'new' 或 'expire'
 * @param {boolean} options.debug - 是否调试模式
 * @returns {Promise<Object>} 扫描结果
 */
export async function scanImage(file, options = {}) {
  const {
    mode = 'dispose',
    itemType = 'food',
    itemState = 'new',
    debug = false,
  } = options;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('mode', mode);
  formData.append('item_type', itemType);
  formData.append('item_state', itemState);
  formData.append('debug', debug ? 'true' : 'false');

  const response = await apiClient.post('/scan/ai', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 60000, // 60 秒超时（AI 分析可能较慢）
  });

  return response.data;
}
