// ============================================================================
// 奖励页面
// ============================================================================

import { useRewards } from '../hooks/useRewards';
import RewardsWallet from '../components/rewards/RewardsWallet';
import RewardsCatalog from '../components/rewards/RewardsCatalog';
import Spinner from '../components/common/Spinner';
import './RewardsPage.css';

export default function RewardsPage() {
  const {
    rewards,
    loading,
    availablePoints,
    claimedCoupons,
    redeem,
  } = useRewards();

  const handleRedeem = async (rewardId) => {
    try {
      const result = await redeem(rewardId);
      alert(`兑换成功！优惠券代码：${result.coupon?.code}`);
    } catch (err) {
      alert('兑换失败：' + err.message);
    }
  };

  if (loading) {
    return <Spinner message="Loading rewards..." />;
  }

  return (
    <section className="tab active">
      <RewardsWallet
        points={availablePoints}
        coupons={claimedCoupons}
      />

      <h3 className="section-title">Eco-Marketplace</h3>

      <RewardsCatalog
        rewards={rewards}
        availablePoints={availablePoints}
        onRedeem={handleRedeem}
      />

      {claimedCoupons.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h3 className="section-title mb-2">My Claimed Coupons</h3>
          <div className="rewards-coupons">
            {claimedCoupons.map((coupon, index) => (
              <div key={index} className="coupon-card">
                <div className="coupon-icon">{coupon.rewardImage}</div>
                <div className="coupon-info">
                  <strong>{coupon.rewardTitle}</strong>
                  <div className="coupon-code">{coupon.code}</div>
                  <small>{coupon.expiry}</small>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
