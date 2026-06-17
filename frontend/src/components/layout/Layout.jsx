// ============================================================================
// 布局组件
// ============================================================================

import { Outlet } from 'react-router-dom';
import Header from './Header';
import Navigation from './Navigation';
import Toast from '../common/Toast';
import './Layout.css';

export default function Layout() {
  return (
    <div className="app">
      <Header />
      <main className="main">
        <Outlet />
      </main>
      <Navigation />
      <Toast />
    </div>
  );
}
