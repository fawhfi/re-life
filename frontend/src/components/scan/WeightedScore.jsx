// ============================================================================
// 加权评分组件
// ============================================================================

import { useState } from 'react';
import './WeightedScore.css';

export default function WeightedScore({
  overallScore,
  grade,
  gradeAdvice,
  gradeColor,
  weightedScores,
  criteriaLabels,
}) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="weighted-section">
      <div className="weighted-header">
        <span className="weighted-title">Weighted Criteria</span>
        <button
          className="weighted-toggle"
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? 'Hide Details' : 'Show Details'}
        </button>
      </div>

      <div className="overall-row">
        <span className="overall-label">Overall Score</span>
        <div>
          <span className="overall-value">{overallScore}</span>
          <span className="overall-max">/100</span>
        </div>
      </div>

      <div className="grade-row">
        <span className="rating-label">Grade</span>
        <span className="grade-tag" style={{ background: gradeColor }}>
          {grade}
        </span>
        <span className="text-muted text-sm font-bold">{gradeAdvice}</span>
      </div>

      <div className="overall-bar">
        <div
          className="overall-bar-fill"
          style={{ width: `${overallScore}%`, background: gradeColor }}
        />
      </div>

      {showDetails && weightedScores && criteriaLabels && (
        <div className="weighted-detail">
          {Object.keys(weightedScores).map((key) => (
            <div key={key} className="criteria-row">
              <span className="criteria-label">{criteriaLabels[key]}</span>
              <div className="criteria-bar">
                <div
                  className="criteria-bar-fill"
                  style={{ width: `${weightedScores[key]}%` }}
                />
              </div>
              <span className="criteria-value">{weightedScores[key]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
