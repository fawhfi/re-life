// ============================================================================
// 记录统计组件
// ============================================================================

import './RecordStats.css';

export default function RecordStats({ stats }) {
  return (
    <div className="stats-bar">
      <div className="stat">
        <div className="stat-number">{stats.count}</div>
        <div className="stat-label">Items</div>
      </div>
      <div className="stat">
        <div className="stat-number">{stats.avgEco}</div>
        <div className="stat-label">Eco Avg</div>
      </div>
      <div className="stat">
        <div className="stat-number">{stats.avgRecycle}</div>
        <div className="stat-label">Recycle Avg</div>
      </div>
    </div>
  );
}
