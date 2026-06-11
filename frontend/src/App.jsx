import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { AppProvider, useApp } from './context/AppContext';
import Header from './components/Header';
import Nav from './components/Nav';
import Home from './pages/Home';
import Record from './pages/Record';
import Rewards from './pages/Rewards';
import Settings from './pages/Settings';
import Login from './pages/Login';
import './App.css';

function AppShell() {
  const { state } = useApp();
  const location = useLocation();

  if (location.pathname === '/login') return <Login />;

  return (
    <div className="app" data-theme={localStorage.getItem('RE_LIFE_THEME') || 'light'}>
      <Header />
      <main className="main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/record" element={<Record />} />
          <Route path="/rewards" element={<Rewards />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
      <Nav />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <AppShell />
      </AppProvider>
    </BrowserRouter>
  );
}
