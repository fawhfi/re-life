import { useNavigate, useLocation } from 'react-router-dom';
import { useState, useRef, useEffect } from 'react';
import { gsap } from 'gsap';

const TABS = [
  { id: 'home', path: '/', icon: '🏠', label: 'Home' },
  { id: 'record', path: '/record', icon: '📋', label: 'Record' },
  { id: 'rewards', path: '/rewards', icon: '🎁', label: 'Rewards' },
  { id: 'settings', path: '/settings', icon: '⋯', label: 'More' },
];

export default function Nav() {
  const navigate = useNavigate();
  const location = useLocation();
  const navRef = useRef(null);
  const indicatorRef = useRef(null);
  const [activeTab, setActiveTab] = useState('home');

  useEffect(() => {
    const tab = TABS.find(t => t.path === location.pathname);
    if (tab) setActiveTab(tab.id);
  }, [location.pathname]);

  useEffect(() => {
    const nav = navRef.current;
    const indicator = indicatorRef.current;
    if (!nav || !indicator) return;

    // Initial snap
    const btn = nav.querySelector(`[data-tab="${activeTab}"]`);
    if (btn) snapTo(btn);

    function snapTo(btn) {
      const nr = nav.getBoundingClientRect();
      const br = btn.getBoundingClientRect();
      const x = br.left - nr.left + (br.width - 90) / 2;
      gsap.to(indicator, {
        left: Math.max(5, Math.min(nr.width - 95, x)),
        width: 90,
        duration: 0.4,
        ease: 'elastic.out(1, 0.6)',
      });
    }

    // Drag handling
    let dragging = false;
    const btns = nav.querySelectorAll('.nav-btn');

    nav.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      dragging = true;
      nav.classList.add('nav-is-dragging');
      nav.setPointerCapture(e.pointerId);
    });

    const move = e => {
      if (!dragging || !indicator) return;
      const nr = nav.getBoundingClientRect();
      const x = e.clientX - nr.left - 45;
      gsap.to(indicator, { left: Math.max(5, Math.min(nr.width - 95, x)), width: 90, duration: 0.08, ease: 'power1.out', overwrite: 'auto' });
    };

    const stop = () => {
      if (!dragging) return;
      dragging = false;
      nav.classList.remove('nav-is-dragging');
      if (indicator) {
        gsap.killTweensOf(indicator);
        indicator.style.transform = '';
        indicator.style.opacity = '';
      }
      const btn = nav.querySelector(`[data-tab="${activeTab}"]`);
      if (btn) snapTo(btn);
    };

    nav.addEventListener('pointermove', move);
    nav.addEventListener('pointerup', stop);
    nav.addEventListener('pointercancel', stop);
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', stop);

    return () => {
      nav.removeEventListener('pointermove', move);
      nav.removeEventListener('pointerup', stop);
      nav.removeEventListener('pointercancel', stop);
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', stop);
    };
  }, [activeTab]);

  return (
    <nav className="nav" ref={navRef}>
      <div className="nav-indicator" ref={indicatorRef} />
      {TABS.map(tab => (
        <button
          key={tab.id}
          data-tab={tab.id}
          className={`nav-btn ${activeTab === tab.id ? 'is-active' : ''}`}
          onClick={() => { setActiveTab(tab.id); navigate(tab.path); }}
        >
          <span className="nav-btn-icon" style={{ fontSize: 18 }}>{tab.icon}</span>
          <span>{tab.label}</span>
        </button>
      ))}
    </nav>
  );
}
