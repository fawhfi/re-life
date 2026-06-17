import { useEffect, useMemo, useState } from 'react';
import './App.css';

const fallbackNews = [
  {
    title: 'Plastic treaty talks are moving again',
    source: 'Reuters',
    snippet: 'Governments are pushing for stronger global rules on plastic waste.',
    link: '#',
  },
  {
    title: 'Cities expand sorting systems for mixed recycling',
    source: 'BBC News',
    snippet: 'AI-assisted sorting is reducing contamination and improving recovery.',
    link: '#',
  },
  {
    title: 'Community recycling points keep growing in HK',
    source: 'SCMP',
    snippet: 'More collection points are arriving near transit and retail hubs.',
    link: '#',
  },
];

const fallbackRewards = [
  {
    title: 'HK$30 grocery voucher',
    provider: 'PARKnSHOP',
    cost: 350,
    emoji: '🎟️',
  },
  {
    title: 'Reusable starter kit',
    provider: 'Green Store HK',
    cost: 400,
    emoji: '🎒',
  },
  {
    title: 'Ocean cleanup sponsor',
    provider: 'Ocean Recovery Alliance',
    cost: 150,
    emoji: '🌊',
  },
];

const quickStats = [
  { label: 'Items scanned', value: 1248, suffix: '+' },
  { label: 'Points earned', value: 84200, suffix: '+' },
  { label: 'Coupons claimed', value: 36, suffix: '' },
];

const heroSignals = [
  { label: 'Sync', value: 'Live' },
  { label: 'Mode', value: 'Mobile ready' },
  { label: 'Motion', value: 'React driven' },
];

const actionItems = [
  {
    title: 'To Dispose',
    description: 'Jump to the disposal flow and see the fastest route.',
    image: '/assets/to_dispose.png',
    target: 'news-section',
  },
  {
    title: 'To Purchase',
    description: 'Scan the reward catalog and compare what the points buy.',
    image: '/assets/to_purchase.png',
    target: 'rewards-section',
  },
];

const sections = [
  { id: 'overview-section', label: 'Overview' },
  { id: 'news-section', label: 'News' },
  { id: 'rewards-section', label: 'Rewards' },
  { id: 'fact-section', label: 'Fact' },
];

function formatTime(value) {
  return new Intl.DateTimeFormat('en-HK', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(value);
}

function formatCompact(value) {
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function easeOutCubic(t) {
  return 1 - Math.pow(1 - t, 3);
}

function MetricCard({ label, value, suffix, delay }) {
  return (
    <article className="metric-card panel reveal" style={{ '--delay': `${delay}ms` }}>
      <div className="metric-value">
        <span>{formatCompact(value)}</span>
        <small>{suffix}</small>
      </div>
      <div className="metric-label">{label}</div>
      <div className="metric-track" aria-hidden="true">
        <span />
      </div>
    </article>
  );
}

function ActionCard({ title, description, image, target, delay }) {
  const scrollToTarget = () => {
    document.getElementById(target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <button
      type="button"
      className="action-card panel reveal"
      style={{ '--delay': `${delay}ms` }}
      onClick={scrollToTarget}
    >
      <img src={image} alt="" className="action-image" />
      <div className="action-copy">
        <div className="action-title">{title}</div>
        <div className="action-subtitle">{description}</div>
      </div>
      <span className="action-arrow" aria-hidden="true">
        →
      </span>
    </button>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [activeSection, setActiveSection] = useState('overview-section');
  const [news, setNews] = useState(fallbackNews);
  const [activeNews, setActiveNews] = useState(0);
  const [newsDirection, setNewsDirection] = useState('next');
  const [rewards, setRewards] = useState(fallbackRewards);
  const [fact, setFact] = useState('Recycling one aluminum can saves enough energy to power a TV for 3 hours.');
  const [syncState, setSyncState] = useState('同步中');
  const [lastSync, setLastSync] = useState('');
  const [clock, setClock] = useState(() => formatTime(new Date()));
  const [statValues, setStatValues] = useState(() => quickStats.map(() => 0));

  useEffect(() => {
    const raf = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setClock(formatTime(new Date())), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!ready) return undefined;

    let raf = 0;
    const start = performance.now();
    const duration = 1100;

    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = easeOutCubic(progress);
      setStatValues(quickStats.map((item) => item.value * eased));
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready]);

  useEffect(() => {
    let alive = true;

    async function loadData() {
      setSyncState('同步中');
      const [newsRes, rewardsRes, factRes] = await Promise.allSettled([
        fetch(`https://re-life-five.vercel.app/api/news?ts=${Date.now()}`, { cache: 'no-store' }),
        fetch('https://re-life-five.vercel.app/api/rewards', { cache: 'no-store' }),
        fetch('https://re-life-five.vercel.app/api/fact', { cache: 'no-store' }),
      ]);

      if (!alive) return;

      if (newsRes.status === 'fulfilled' && newsRes.value.ok) {
        const items = await newsRes.value.json();
        if (Array.isArray(items) && items.length) {
          setNews(
            items.map((item) => ({
              title: item.title || 'Untitled update',
              source: item.source || 'Google News',
              snippet: item.snippet || '',
              link: item.link || '#',
            })),
          );
        }
      }

      if (rewardsRes.status === 'fulfilled' && rewardsRes.value.ok) {
        const items = await rewardsRes.value.json();
        if (Array.isArray(items) && items.length) {
          setRewards(
            items.slice(0, 3).map((item) => ({
              title: item.title,
              provider: item.provider,
              cost: item.cost,
              emoji: item.image || '♻️',
            })),
          );
        }
      }

      if (factRes.status === 'fulfilled' && factRes.value.ok) {
        const data = await factRes.value.json();
        if (data?.fact) setFact(data.fact);
      }

      setSyncState('已同步');
      setLastSync(
        new Intl.DateTimeFormat('en-HK', {
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        }).format(new Date()),
      );
    }

    loadData().catch(() => {
      if (alive) setSyncState('离线模式');
    });

    const refresh = () => {
      if (!document.hidden) loadData().catch(() => {});
    };

    document.addEventListener('visibilitychange', refresh);
    window.addEventListener('focus', refresh);
    window.addEventListener('online', refresh);

    return () => {
      alive = false;
      document.removeEventListener('visibilitychange', refresh);
      window.removeEventListener('focus', refresh);
      window.removeEventListener('online', refresh);
    };
  }, []);

  useEffect(() => {
    if (news.length < 2) return undefined;

    const timer = setInterval(() => {
      setNewsDirection('next');
      setActiveNews((current) => (current + 1) % news.length);
    }, 6200);

    return () => clearInterval(timer);
  }, [news.length]);

  useEffect(() => {
    const targets = sections
      .map((section) => document.getElementById(section.id))
      .filter(Boolean);

    if (!targets.length) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

        if (visible?.target?.id) {
          setActiveSection(visible.target.id);
        }
      },
      {
        root: null,
        threshold: [0.2, 0.35, 0.5, 0.7],
        rootMargin: '-10% 0px -55% 0px',
      },
    );

    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  const currentNews = useMemo(() => news[activeNews] || news[0], [news, activeNews]);
  const newsProgress = news.length ? ((activeNews + 1) / news.length) * 100 : 0;

  const goToNews = (nextIndex, direction) => {
    setNewsDirection(direction);
    setActiveNews(nextIndex);
  };

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setActiveSection(id);
  };

  return (
    <div className={`app-shell ${ready ? 'is-ready' : ''}`}>
      <div className="shell-backdrop" aria-hidden="true" />

      <header className="topbar reveal" style={{ '--delay': '0ms' }}>
        <div className="brand-lockup">
          <img src="/assets/Logo.png" alt="Re-Life" className="brand-logo" />
          <div className="brand-copy">
            <div className="brand-name">Re-Life</div>
            <div className="brand-subtitle">React dashboard</div>
          </div>
        </div>

        <div className="status-cluster">
          <div className={`status-chip ${syncState === '离线模式' ? 'is-warn' : ''}`}>
            <span className="status-dot" />
            <span>{syncState}</span>
          </div>
          <div className="clock-chip">{clock}</div>
        </div>
      </header>

      <main className="dashboard">
        <nav className="section-switcher panel reveal" style={{ '--delay': '60ms' }} aria-label="Section navigation">
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? 'switcher-chip is-active' : 'switcher-chip'}
              onClick={() => scrollToSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>

        <section id="overview-section" className="hero-panel panel reveal" style={{ '--delay': '80ms' }}>
          <div className="hero-copy">
            <span className="eyebrow">Live recycling intelligence</span>
            <h1>Refined motion for a greener daily loop.</h1>
            <p>
              A faster, cleaner React front end with richer visual rhythm, sharper hierarchy, and motion that respects
              the content.
            </p>

            <div className="hero-actions">
              <button
                type="button"
                className="button button--primary"
                onClick={() => document.getElementById('news-section')?.scrollIntoView({ behavior: 'smooth' })}
              >
                Explore the feed
              </button>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => document.getElementById('rewards-section')?.scrollIntoView({ behavior: 'smooth' })}
              >
                See rewards
              </button>
            </div>

            <div className="hero-summary">
              <div className="summary-card">
                <span>Today</span>
                <strong>Scan, compare, claim</strong>
              </div>
              <div className="summary-card">
                <span>Focus</span>
                <strong>Fewer taps, clearer flow</strong>
              </div>
            </div>

            <div className="hero-signals">
              {heroSignals.map((item, index) => (
                <div className="signal-chip" key={item.label} style={{ '--delay': `${index * 70 + 120}ms` }}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="hero-visual">
            <div className="hero-frame">
              <img src="/assets/hero.png" alt="Re-Life hero preview" className="hero-image" />
              <div className="hero-caption">
                <div>
                  <span className="caption-label">Current state</span>
                  <strong>{syncState}</strong>
                </div>
                <div className="caption-meta">{lastSync ? `Synced ${lastSync}` : 'Waiting for first sync'}</div>
              </div>
            </div>
          </div>
        </section>

        <section className="stats-row">
          {quickStats.map((item, index) => (
            <MetricCard
              key={item.label}
              label={item.label}
              value={statValues[index] || 0}
              suffix={item.suffix}
              delay={140 + index * 80}
            />
          ))}
        </section>

        <section className="action-grid">
          {actionItems.map((item, index) => (
            <ActionCard key={item.title} {...item} delay={180 + index * 90} />
          ))}
        </section>

        <section className="content-grid">
          <article id="news-section" className="panel news-panel reveal" style={{ '--delay': '320ms' }}>
            <div className="panel-topline">
              <div>
                <span className="eyebrow">Green news</span>
                <h2>What is moving right now</h2>
              </div>
              <div className="news-count">
                <span className="news-count-value">{activeNews + 1}</span>
                <span>/ {news.length}</span>
              </div>
            </div>

            <div className={`news-stage news-stage--${newsDirection}`} key={`${activeNews}-${currentNews?.title}`}>
              <div className="news-kicker">{currentNews?.source}</div>
              <h3>{currentNews?.title}</h3>
              <p>{currentNews?.snippet}</p>
              <a
                className={`news-link ${currentNews?.link === '#' ? 'is-disabled' : ''}`}
                href={currentNews?.link === '#' ? undefined : currentNews?.link}
                target={currentNews?.link === '#' ? undefined : '_blank'}
                rel={currentNews?.link === '#' ? undefined : 'noreferrer'}
                aria-disabled={currentNews?.link === '#'}
                onClick={(event) => currentNews?.link === '#' && event.preventDefault()}
              >
                Open story
              </a>
            </div>

            <div className="news-meta">
              <div className="news-progress">
                <span style={{ width: `${newsProgress}%` }} />
              </div>
              <div className="panel-actions">
                <button
                  type="button"
                  className="button button--chip"
                  onClick={() => goToNews((activeNews - 1 + news.length) % news.length, 'prev')}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button button--chip"
                  onClick={() => goToNews((activeNews + 1) % news.length, 'next')}
                >
                  Next
                </button>
              </div>
            </div>

            <div className="dots" aria-hidden="true">
              {news.map((item, index) => (
                <button
                  key={`${item.title}-${index}`}
                  type="button"
                  className={index === activeNews ? 'dot is-active' : 'dot'}
                  onClick={() => goToNews(index, index < activeNews ? 'prev' : 'next')}
                  aria-label={`View news ${index + 1}`}
                />
              ))}
            </div>
          </article>

          <article id="rewards-section" className="panel rewards-panel reveal" style={{ '--delay': '380ms' }}>
            <div className="panel-topline">
              <div>
                <span className="eyebrow">Rewards</span>
                <h2>What the points can become</h2>
              </div>
              <img src="/assets/Reward.png" alt="" className="panel-icon" />
            </div>

            <div className="reward-list">
              {rewards.map((item, index) => (
                <div className="reward-item" key={item.title} style={{ '--delay': `${index * 90}ms` }}>
                  <span className="reward-emoji">{item.emoji}</span>
                  <div className="reward-copy">
                    <strong>{item.title}</strong>
                    <span>{item.provider}</span>
                  </div>
                  <div className="reward-cost">{item.cost}</div>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section id="fact-section" className="fact-panel panel reveal" style={{ '--delay': '460ms' }}>
          <div className="fact-icon-wrap">
            <img src="/assets/Scan.png" alt="" className="fact-icon" />
          </div>
          <div className="fact-copy">
            <span className="eyebrow">Did you know?</span>
            <p>{fact}</p>
          </div>
          <div className="fact-badge">
            <span className="fact-badge-label">Sync</span>
            <strong>{syncState}</strong>
          </div>
        </section>
      </main>
    </div>
  );
}
