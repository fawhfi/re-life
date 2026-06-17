// ============================================================================
// 底部导航组件
// ============================================================================

import { NavLink } from 'react-router-dom';
import './Navigation.css';

export default function Navigation() {
  const navItems = [
    { path: '/', label: 'Home', icon: '🏠' },
    { path: '/records', label: 'Record', icon: '📝' },
    { path: '/rewards', label: 'Rewards', icon: '🎁' },
    { path: '/settings', label: 'More', icon: '⚙️' },
  ];

  return (
    <nav className="nav">
      <div className="nav-indicator" />
      {navItems.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) =>
            isActive ? 'nav-btn is-active' : 'nav-btn'
          }
        >
          <span className="nav-btn-icon">{item.icon}</span>
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
