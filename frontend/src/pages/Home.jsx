import { useState, useRef } from 'react';
import { useApp } from '../context/AppContext';

export default function Home() {
  const { state, updateState } = useApp();
  const [preview, setPreview] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef(null);

  const handleFile = async (file) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    setScanning(true);
    setResult(null);

    const fd = new FormData();
    fd.append('file', file);
    fd.append('mode', state.scanMode);

    try {
      const res = await fetch('/api/scan', { method: 'POST', body: fd });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ error: 'Scan failed. Please try again.' });
    } finally {
      setScanning(false);
    }
  };

  const addToRecord = async () => {
    if (!result || !state.currentUser) return;
    const record = {
      ...result,
      id: Date.now().toString(),
      userId: state.userId,
      timestamp: new Date().toISOString(),
    };
    try {
      const FB = window.FB;
      if (FB) await FB.addItem(record);
      updateState({ records: [record, ...state.records], lastScanResult: null });
      setResult(null);
      setPreview(null);
    } catch (e) {
      console.error('Failed to save record:', e);
    }
  };

  return (
    <section className="tab active" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Scan mode toggles */}
      <div className="card" style={{ padding: 14 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={`scan-btn scan-btn--dispose ${state.scanMode === 'dispose' ? 'scan-btn--active' : ''}`}
            onClick={() => updateState({ scanMode: 'dispose' })}
          >
            <div className="scan-btn-icon" style={{ fontSize: 24 }}>♻️</div>
            <span style={{ fontSize: 11, fontWeight: 700 }}>DISPOSE</span>
          </button>
          <button
            className={`scan-btn scan-btn--purchase ${state.scanMode === 'purchase' ? 'scan-btn--active' : ''}`}
            onClick={() => updateState({ scanMode: 'purchase' })}
          >
            <div className="scan-btn-icon" style={{ fontSize: 24 }}>🛒</div>
            <span style={{ fontSize: 11, fontWeight: 700 }}>PURCHASE</span>
          </button>
        </div>
      </div>

      {/* Upload zone */}
      <div
        className="upload-zone"
        onClick={() => fileRef.current?.click()}
        onDrop={e => { e.preventDefault(); handleFile(e.dataTransfer.files[0]); }}
        onDragOver={e => e.preventDefault()}
      >
        {preview ? (
          <div className="upload-preview is-shown">
            <img src={preview} alt="Preview" style={{ maxWidth: '100%', maxHeight: 160, borderRadius: 10 }} />
            <button className="upload-preview-remove" onClick={e => { e.stopPropagation(); setPreview(null); setResult(null); }}>×</button>
          </div>
        ) : (
          <>
            <div className="upload-zone-icon" style={{ fontSize: 32 }}>📷</div>
            <div className="upload-zone-text">Tap to scan</div>
            <div className="upload-zone-sub">or drag &amp; drop</div>
          </>
        )}
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden
               onChange={e => handleFile(e.target.files[0])} />
      </div>

      {/* Scanning indicator */}
      {scanning && (
        <div className="card" style={{ textAlign: 'center', padding: 20 }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
          <div style={{ fontWeight: 600 }}>AI Analyzing...</div>
          <div style={{ fontSize: 12, color: 'var(--color-gray-400)', marginTop: 4 }}>Evaluating your item</div>
        </div>
      )}

      {/* Result */}
      {result && !result.error && (
        <div className="result-card" style={{ padding: 20 }}>
          <h3 style={{ margin: 0 }}>{result.name || 'Scanned Item'}</h3>
          <p style={{ fontSize: 13, color: 'var(--color-gray-500)' }}>{result.description}</p>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn--primary" onClick={addToRecord}>Add to Record</button>
            <button className="btn btn--outline" onClick={() => { setResult(null); setPreview(null); }}>Scan Again</button>
          </div>
        </div>
      )}

      {result?.error && (
        <div className="card" style={{ textAlign: 'center', color: 'var(--color-red-500)' }}>
          {result.error}
        </div>
      )}
    </section>
  );
}
