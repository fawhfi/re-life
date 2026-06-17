// ============================================================================
// 数据 API（新闻、奖励、知识等）
// ============================================================================

import apiClient from './client';

/**
 * 获取环保新闻
 * @returns {Promise<Array>} 新闻数组
 */
export async function getNews() {
  const response = await apiClient.get('/news', {
    params: { ts: Date.now() }, // 避免缓存
  });
  return response.data;
}

/**
 * 获取评分模式配置
 * @returns {Promise<Object>} 模式配置
 */
export async function getSchemas() {
  const response = await apiClient.get('/schemas');
  return response.data;
}

/**
 * 获取奖励目录
 * @returns {Promise<Array>} 奖励数组
 */
export async function getRewards() {
  const response = await apiClient.get('/rewards');
  return response.data;
}

/**
 * 兑换奖励
 * @param {string} rewardId - 奖励 ID
 * @param {number} userPoints - 用户当前积分
 * @returns {Promise<Object>} 兑换结果（包含优惠券）
 */
export async function redeemReward(rewardId, userPoints) {
  const response = await apiClient.post('/rewards/redeem', {
    reward_id: rewardId,
    user_points: userPoints,
  });
  return response.data;
}

/**
 * 获取环保知识
 * @returns {Promise<Object>} 知识对象 { fact: string }
 */
export async function getFact() {
  const response = await apiClient.get('/fact');
  return response.data;
}
