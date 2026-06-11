import { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';

export default function Record() {
  const { state } = useApp();
  const [records, setRecords] = useState([]);

  useEffect(() => {
    const FB = window.FB;
    if (!FB || !state.currentUser) return;
    FB.getItems(state.userId, state.currentUser, state.userKey).then(items => {
      setRecords(items || []);
    });
  }, [state.currentUser]);

  return (
    <section className="tab active" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="stats-bar" style={{ display: 'flex', justifyContent: 'space-around' }}>
          <div className="stat"><div className="stat-number">{records.length}</div><div className="stat-label">Items</div></div>
          <div className="stat"><div className="stat-number">--</div><div className="stat-label">Eco Avg</div></div>
          <div className="stat"><div className="stat-number">--</div><div className="stat-label">Recycle Avg</div></div>
        </div>
      </div>

      {records.length === 0 ? (
        <div className="empty-state" style={{ textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 48, opacity: 0.3 }}>📋</div>
          <div>No records yet</div>
          <div style={{ fontSize: 12, color: 'var(--color-gray-400)' }}>Start by scanning an item</div>
        </div>
      ) : (
        records.map(r => (
          <div key={r.id} className="record-card" style={{ padding: 14, borderRadius: 14, background: 'var(--color-white)', border: '1px solid var(--color-gray-200)' }}>
            <div style={{ fontWeight: 600 }}>{r.name || r.category}</div>
            <div style={{ fontSize: 12, color: 'var(--color-gray-400)' }}>{r.description}</div>
          </div>
        ))
      )}
    </section>
  );
}
