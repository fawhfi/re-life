// ============================================================================
// 加载动画组件
// ============================================================================

import './Spinner.css';

export default function Spinner({
  size = 'medium',
  message = '',
}) {
  return (
    <div className={`spinner-container spinner--${size}`}>
      <div className="spinner">
        <div className="spinner-ring" />
        <div className="spinner-ring" />
        <div className="spinner-ring" />
      </div>
      {message && <div className="spinner-message">{message}</div>}
    </div>
  );
}
