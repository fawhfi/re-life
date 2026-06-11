import { useApp } from '../context/AppContext';

export default function Rewards() {
  const { state } = useApp();
  const balance = Math.max(0, (state.earnedPoints || 0) - (state.spentPoints || 0));

  return (
    <section className="tab active" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="rewards-wallet" style={{ background: 'var(--color-primary)', color: '#fff', borderRadius: 14, padding: 18 }}>
        <div style={{ fontSize: 12, opacity: 0.7 }}>Eco Points Balance</div>
        <div style={{ fontSize: 32, fontWeight: 900 }}>🪙 {balance}</div>
        <div style={{ fontSize: 11, opacity: 0.6 }}>Points available</div>
      </div>
      <div style={{ textAlign: 'center', color: 'var(--color-gray-400)', fontSize: 13, padding: 20 }}>
        Rewards marketplace coming soon
      </div>
    </section>
  );
}
