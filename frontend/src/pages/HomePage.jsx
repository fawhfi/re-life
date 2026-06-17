// ============================================================================
// 首页
// ============================================================================

import { useState } from 'react';
import { useScan } from '../hooks/useScan';
import ScanUploader from '../components/scan/ScanUploader';
import ScanResult from '../components/scan/ScanResult';
import './HomePage.css';

export default function HomePage() {
  const {
    mode,
    result,
    loading,
    error,
    setMode,
    selectAndScan,
    reset,
  } = useScan();

  const [showResult, setShowResult] = useState(false);

  const handleScan = async (file) => {
    try {
      await selectAndScan(file);
      setShowResult(true);
    } catch (err) {
      console.error('Scan failed:', err);
    }
  };

  const handleReset = () => {
    reset();
    setShowResult(false);
  };

  return (
    <section className="tab active">
      <div className="card">
        <h2 className="card-header">SCAN YOUR ITEMS</h2>
        <div className="scan-grid">
          <button
            className={`scan-btn scan-btn--dispose ${mode === 'dispose' ? 'active' : ''}`}
            onClick={() => setMode('dispose')}
          >
            <div className="scan-btn-icon">♻️</div>
            <span className="scan-btn-label">TO DISPOSE</span>
          </button>
          <button
            className={`scan-btn scan-btn--purchase ${mode === 'purchase' ? 'active' : ''}`}
            onClick={() => setMode('purchase')}
          >
            <div className="scan-btn-icon">🛒</div>
            <span className="scan-btn-label">TO PURCHASE</span>
          </button>
        </div>
      </div>

      {!showResult && (
        <ScanUploader
          onScan={handleScan}
          loading={loading}
          error={error}
        />
      )}

      {showResult && result && (
        <ScanResult
          result={result}
          mode={mode}
          onReset={handleReset}
        />
      )}

      <div className="fact-card">
        <span className="fact-card-icon">🏆</span>
        <div>
          <div className="fact-card-title">Did you know?</div>
          <div className="fact-card-text">
            Recycling a single aluminum can saves enough energy to power a TV for 3 hours.
          </div>
        </div>
      </div>
    </section>
  );
}
