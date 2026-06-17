// ============================================================================
// 奖励钱包组件
// ============================================================================

import './RewardsWallet.css';

export default function RewardsWallet({ points, coupons }) {
  return (
    <div className="rewards-wallet">
      <div className="rewards-label">Eco Points Balance</div>
      <div className="rewards-points">
        🪙 <span>{points}</span>
      </div>
      <div className="rewards-sub">
        Convert your choices into real-world action.
      </div>
      {coupons.length > 0 && (
        <div className="rewards-shortcut">
          <span className="text-sm font-bold" style={{ color: 'var(--color-emerald-200)' }}>
            My Coupons
          </span>
          <button
            className="rew-view-btn"
            onClick={() => {
              document.getElementById('my-coupons')?.scrollIntoView({ behavior: 'smooth' });
            }}
          >
            🎫 View Claimed ({coupons.length})
          </button>
        </div>
      )}
    </div>
  );
}
