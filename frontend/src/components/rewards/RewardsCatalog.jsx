// ============================================================================
// 奖励目录组件
// ============================================================================

import Button from '../common/Button';
import './RewardsCatalog.css';

export default function RewardsCatalog({ rewards, availablePoints, onRedeem }) {
  return (
    <div className="rewards-catalog">
      {rewards.map((reward) => {
        const canAfford = availablePoints >= reward.cost;

        return (
          <div key={reward.id} className="reward-item">
            <span className="reward-emoji">{reward.image}</span>

            <div className="reward-content">
              <div className="reward-header">
                <strong className="reward-title">{reward.title}</strong>
                <span className="reward-cost">{reward.cost} pts</span>
              </div>

              <div className="reward-provider">{reward.provider}</div>
              <div className="reward-description">{reward.description}</div>

              <Button
                size="small"
                variant={canAfford ? 'primary' : 'outline'}
                disabled={!canAfford}
                onClick={() => onRedeem(reward.id)}
              >
                {canAfford ? 'Redeem' : 'Not Enough Points'}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
