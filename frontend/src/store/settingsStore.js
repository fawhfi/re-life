// ============================================================================
// 设置状态管理（积分、优惠券等）
// ============================================================================

import { create } from 'zustand';
import { storage } from '../utils/storage';

export const useSettingsStore = create((set, get) => ({
  // 积分
  earnedPoints: storage.get('EARNED_POINTS', 0),
  spentPoints: storage.get('SPENT_POINTS', 0),

  // 优惠券
  claimedCoupons: storage.get('CLAIMED_COUPONS', []),

  // 计算可用积分
  getAvailablePoints: () => {
    const { earnedPoints, spentPoints } = get();
    return earnedPoints - spentPoints;
  },

  // 增加积分
  addPoints: (points) => set((state) => {
    const earnedPoints = state.earnedPoints + points;
    storage.set('EARNED_POINTS', earnedPoints);
    return { earnedPoints };
  }),

  // 扣除积分
  spendPoints: (points) => set((state) => {
    const spentPoints = state.spentPoints + points;
    storage.set('SPENT_POINTS', spentPoints);
    return { spentPoints };
  }),

  // 添加优惠券
  addCoupon: (coupon) => set((state) => {
    const claimedCoupons = [...state.claimedCoupons, {
      ...coupon,
      claimedAt: Date.now(),
    }];
    storage.set('CLAIMED_COUPONS', claimedCoupons);
    return { claimedCoupons };
  }),

  // 重置所有设置
  reset: () => {
    storage.remove('EARNED_POINTS');
    storage.remove('SPENT_POINTS');
    storage.remove('CLAIMED_COUPONS');
    set({
      earnedPoints: 0,
      spentPoints: 0,
      claimedCoupons: [],
    });
  },
}));
