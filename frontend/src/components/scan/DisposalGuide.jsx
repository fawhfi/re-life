// ============================================================================
// 处理指南组件
// ============================================================================

import './DisposalGuide.css';

export default function DisposalGuide({
  disposalInfo,
  disposalGuide,
  precaution,
}) {
  if (!disposalInfo) return null;

  return (
    <div className="disposal-guide">
      <div className="disposal-guide-title">♻️ Disposal Guide</div>

      <div className="disposal-guide-row">
        <span className="disposal-guide-label">Material:</span>
        <span>{disposalInfo.type}</span>
      </div>

      <div className="disposal-guide-row">
        <span className="disposal-guide-label">Method:</span>
        <span>{disposalInfo.method}</span>
      </div>

      <div className="disposal-guide-row">
        <span className="disposal-guide-label">Location:</span>
        <span>{disposalInfo.location}</span>
      </div>

      {disposalGuide && (
        <div className="disposal-guide-row mt-2">{disposalGuide}</div>
      )}

      {precaution && (
        <div className="disposal-guide-precaution">{precaution}</div>
      )}
    </div>
  );
}
