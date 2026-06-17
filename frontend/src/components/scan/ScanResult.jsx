// ============================================================================
// 扫描结果组件
// ============================================================================

import { useState } from 'react';
import { useRecords } from '../../hooks/useRecords';
import WeightedScore from './WeightedScore';
import DisposalGuide from './DisposalGuide';
import Button from '../common/Button';
import { renderStars } from '../../utils/scoring';
import './ScanResult.css';

export default function ScanResult({ result, mode, onReset }) {
  const { addRecord } = useRecords();
  const [saving, setSaving] = useState(false);

  const handleAddToRecord = async () => {
    setSaving(true);
    try {
      await addRecord(result);
      alert('已添加到记录！');
      onReset();
    } catch (err) {
      alert('添加失败：' + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="result-card">
      {result.image_url && (
        <div className="record-card-image">
          <img src={result.image_url} alt={result.name} />
        </div>
      )}

      <div className="result-card-name">{result.name}</div>
      {result.brand && (
        <div className="result-card-tip font-bold">{result.brand}</div>
      )}
      <div className="result-card-tip">{result.description}</div>

      <div className="record-card-ratings flex-center mt-3">
        <div className="rating-item">
          <span className="rating-label">Eco-Rate</span>
          <div className="star-rating">{renderStars(result.eco_rate)}</div>
        </div>
        <div className="rating-item">
          <span className="rating-label">Recycle Rate</span>
          <div className="star-rating">{renderStars(result.recycle_rate)}</div>
        </div>
      </div>

      {mode === 'purchase' && result.alternative && (
        <div className="alternative-card">
          <div className="alternative-card-label">Alternative Product</div>
          <div className="alternative-card-name">{result.alternative.name}</div>
          <div className="alternative-card-ratings">
            <div className="rating-item">
              <span className="rating-label">Eco-Rate:</span>
              <div className="star-rating">{renderStars(result.alternative.eco_rate)}</div>
            </div>
            <div className="rating-item">
              <span className="rating-label">Recycle Rate:</span>
              <div className="star-rating">{renderStars(result.alternative.recycle_rate)}</div>
            </div>
          </div>
        </div>
      )}

      <WeightedScore
        overallScore={result.overall_score}
        grade={result.grade}
        gradeAdvice={result.grade_advice}
        gradeColor={result.grade_color}
        weightedScores={result.weighted_scores}
        criteriaLabels={result.criteria_labels}
      />

      {result.disposal_info && (
        <DisposalGuide
          disposalInfo={result.disposal_info}
          disposalGuide={result.disposal_guide}
          precaution={result.precaution}
        />
      )}

      <div className="result-card-actions">
        <Button variant="outline" onClick={onReset}>
          Scan Again
        </Button>
        <Button onClick={handleAddToRecord} loading={saving}>
          Add to Record
        </Button>
      </div>
    </div>
  );
}
