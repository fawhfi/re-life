// ============================================================================
// 奖励相关 Hook
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import { useSettingsStore } from '../store/settingsStore';
import { getRewards, redeemReward } from '../api/data';

/**
 * 奖励 Hook
 * @returns {Object} 奖励相关状态和方法
 */
export function useRewards() {
  const {
    earnedPoints,
    spentPoints,
    claimedCoupons,
    getAvailablePoints,
    spendPoints,
    addCoupon,
  } = useSettingsStore();

  const [rewards, setRewards] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const availablePoints = getAvailablePoints();

  // 加载奖励目录
  const loadRewards = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const data = await getRewards();
      setRewards(data);
    } catch (err) {
      console.error('[Rewards] Load failed:', err);
      setError(err.message || 'Failed to load rewards');
    } finally {
      setLoading(false);
    }
  }, []);

  // 兑换奖励
  const redeem = useCallback(async (rewardId) => {
    const reward = rewards.find(r => r.id === rewardId);
    if (!reward) {
      throw new Error('Reward not found');
    }

    if (availablePoints < reward.cost) {
      throw new Error('Not enough points');
    }

    try {
      const result = await redeemReward(rewardId, availablePoints);

      // 扣除积分
      spendPoints(reward.cost);

      // 添加优惠券
      if (result.coupon) {
        addCoupon({
          ...result.coupon,
          rewardId,
          rewardTitle: reward.title,
          rewardImage: reward.image,
        });
      }

      return result;
    } catch (err) {
      console.error('[Rewards] Redeem failed:', err);
      throw err;
    }
  }, [rewards, availablePoints, spendPoints, addCoupon]);

  // 初始加载
  useEffect(() => {
    loadRewards();
  }, [loadRewards]);

  return {
    rewards,
    loading,
    error,
    earnedPoints,
    spentPoints,
    availablePoints,
    claimedCoupons,
    loadRewards,
    redeem,
  };
}
