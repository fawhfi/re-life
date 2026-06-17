// ============================================================================
// 扫描上传组件
// ============================================================================

import { useRef, useState } from 'react';
import Spinner from '../common/Spinner';
import './ScanUploader.css';

export default function ScanUploader({ onScan, loading, error }) {
  const fileInputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      onScan(file);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);

    const file = e.dataTransfer.files?.[0];
    if (file) {
      onScan(file);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  if (loading) {
    return (
      <div className="scanning-status">
        <Spinner message="AI Analyzing..." />
        <div className="scanning-hint">AI is evaluating your item</div>
      </div>
    );
  }

  return (
    <div
      className={`upload-zone ${dragging ? 'dragging' : ''}`}
      onClick={triggerFileInput}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      <div className="upload-zone-icon">📷</div>
      <div className="upload-zone-text">Tap to scan</div>
      <div className="upload-zone-sub">or drag & drop anywhere</div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />

      {error && (
        <div className="upload-error">{error}</div>
      )}
    </div>
  );
}
