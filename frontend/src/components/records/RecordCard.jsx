// ============================================================================
// 记录卡片组件
// ============================================================================

import { renderStars } from '../../utils/scoring';
import './RecordCard.css';

export default function RecordCard({ record, onDelete }) {
  const formatDate = (timestamp) => {
    return new Date(timestamp).toLocaleDateString('en-HK', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <div className="record-card">
      {record.photoUrl && (
        <div className="record-card-image">
          <img src={record.photoUrl} alt={record.name} />
        </div>
      )}

      <div className="record-card-content">
        <div className="record-card-header">
          <h3 className="record-card-name">{record.name}</h3>
          <button className="record-card-delete" onClick={onDelete}>
            ×
          </button>
        </div>

        {record.brand && (
          <div className="record-card-brand">{record.brand}</div>
        )}

        <div className="record-card-description">{record.description}</div>

        <div className="record-card-ratings">
          <div className="rating-item">
            <span className="rating-label">Eco:</span>
            <div className="star-rating">{renderStars(record.eco_rate)}</div>
          </div>
          <div className="rating-item">
            <span className="rating-label">Recycle:</span>
            <div className="star-rating">{renderStars(record.recycle_rate)}</div>
          </div>
        </div>

        {record.overall_score && (
          <div className="record-card-score">
            Score: <strong>{record.overall_score}/100</strong>
            {record.grade && <span className="record-card-grade">{record.grade}</span>}
          </div>
        )}

        <div className="record-card-footer">
          <span className="record-card-date">{formatDate(record.createdAt)}</span>
          <span className={`record-card-status status-${record.status}`}>
            {record.status}
          </span>
        </div>
      </div>
    </div>
  );
}
