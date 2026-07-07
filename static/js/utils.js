/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Utilities
   Pure functions + safeStorage + beeps. No DOM dependencies except
   renderStars (which needs document.getElementById).
   ═══════════════════════════════════════════════════════════════════════ */

const MOTION_PROFILE = (() => {
    const reducedMotion = !!(typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    const doc = typeof document !== 'undefined' ? document.documentElement : null;
    const forcedLite = !!(doc && doc.classList.contains('perf-lite'));
    const connection = typeof navigator !== 'undefined' ? (navigator.connection || navigator.mozConnection || navigator.webkitConnection) : null;
    const saveData = !!(connection && connection.saveData);
    const deviceMemory = typeof navigator !== 'undefined' && typeof navigator.deviceMemory === 'number' ? navigator.deviceMemory : null;
    const lowEnd = forcedLite || saveData || (!!deviceMemory && deviceMemory <= 4);
    return { reducedMotion, lowEnd, motionEnabled: !(reducedMotion || lowEnd) };
})();

if (typeof document !== 'undefined' && document.documentElement && (MOTION_PROFILE.lowEnd || MOTION_PROFILE.reducedMotion)) {
    document.documentElement.classList.add('perf-lite');
}
if (typeof window !== 'undefined') {
    window.RELIFE_PERF = MOTION_PROFILE;
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function buildStars(rating) {
    const r = Math.round(rating);
    let h = '';
    for (let i = 1; i <= 5; i++) {
        const filled = i <= r;
        h += `<span class="star ${filled ? 'is-filled' : ''}" data-index="${i}" style="${filled ? 'opacity:0;transform:scale(0.5)' : ''}">★</span>`;
    }
    h += `<span class="rating-value">${r}/5</span>`;
    return h;
}

function renderStars(id, rating) {
    const el = document.getElementById(id);
    if (!el) return;
    const oldEls = el.querySelectorAll('.star');
    el.innerHTML = buildStars(rating);

    // Animate stars in with GSAP if available
    if (typeof window.gsap !== 'undefined' && window.gsap.to && typeof window.gsap.to === 'function') {
        const filledStars = el.querySelectorAll('.star.is-filled');
        if (filledStars.length) {
            window.gsap.fromTo(filledStars,
                { opacity: 0, scale: 0.5, rotate: -15 },
                {
                    opacity: 1, scale: 1, rotate: 0,
                    duration: 0.4,
                    stagger: 0.07,
                    ease: 'back.out(1.7)',
                    clearProps: 'transform',
                }
            );
        }
    } else {
        // Fallback: just show them
        el.querySelectorAll('.star.is-filled').forEach(s => {
            s.style.opacity = '1';
            s.style.transform = 'none';
        });
    }
}

function calcWeighted(scores, schemaId) {
    const w = SCHEMA_WEIGHTS[schemaId] || SCHEMA_WEIGHTS.food_new;
    return Math.round(
        (scores.a || 50) * w.a + (scores.b || 50) * w.b +
        (scores.c || 50) * w.c + (scores.d || 50) * w.d +
        (scores.e || 50) * w.e
    );
}

function isDarkMode() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
}

function getGrade(score) {
    const dark = isDarkMode();
    if (score >= 85) return { grade: 'Excellent (A)', advice: 'Highly Recommended', color: dark ? '#4ade80' : '#065f46' };
    if (score >= 70) return { grade: 'Good (B)', advice: 'Acceptable', color: dark ? '#34d399' : '#047857' };
    if (score >= 55) return { grade: 'Fair (C)', advice: 'Consider Alternatives', color: dark ? '#fbbf24' : '#ca8a04' };
    if (score >= 40) return { grade: 'Poor (D)', advice: 'Avoid if Possible', color: dark ? '#f97316' : '#b45309' };
    return { grade: 'Very Poor (E)', advice: 'Strongly Discouraged', color: dark ? '#f87171' : '#dc2626' };
}

function getBarColor(v) {
    const dark = isDarkMode();
    if (v >= 70) return dark ? '#4ade80' : '#065f46';
    if (v >= 50) return dark ? '#fbbf24' : '#ca8a04';
    return dark ? '#f87171' : '#dc2626';
}

const safeStorage = {
    _mem: {},
    get(k) { try { return localStorage.getItem(k); } catch { return this._mem[k] || null; } },
    set(k, v) { try { localStorage.setItem(k, String(v)); } catch { this._mem[k] = String(v); } },
    remove(k) { try { localStorage.removeItem(k); } catch { delete this._mem[k]; } },
};

function animateNumber(elementId, start, end, duration = 800) {
    const obj = document.getElementById(elementId);
    if (!obj) return;
    const target = Number(end);
    const initial = Number(start);
    if (!MOTION_PROFILE.motionEnabled || !Number.isFinite(target) || !Number.isFinite(initial) || initial === target) {
        obj.textContent = Number.isFinite(target) ? target.toLocaleString() : String(end);
        return;
    }
    const decimals = String(end).includes('.') ? Math.min(1, String(end).split('.')[1].length) : 0;

    // Use GSAP for smoother animation if available
    if (typeof window.gsap !== 'undefined' && window.gsap.to && typeof window.gsap.to === 'function') {
        const wrapper = { val: initial };
        window.gsap.killTweensOf(wrapper);
        window.gsap.to(wrapper, {
            val: target,
            duration: Math.min(duration, 1500) / 1000,
            ease: 'power2.out',
            onUpdate: () => {
                obj.textContent = decimals ? wrapper.val.toFixed(decimals) : Math.floor(wrapper.val).toLocaleString();
            },
            onComplete: () => {
                obj.textContent = decimals ? target.toFixed(decimals) : target.toLocaleString();
            },
        });
        return;
    }

    // Fallback: requestAnimationFrame
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 5);
        const value = initial + (target - initial) * ease;
        obj.textContent = decimals ? value.toFixed(decimals) : Math.floor(value).toLocaleString();
        if (progress < 1) { requestAnimationFrame(step); } else { obj.textContent = decimals ? target.toFixed(decimals) : target.toLocaleString(); }
    };
    requestAnimationFrame(step);
}

let soundOn = true;
function playBeep(type) {
    if (!soundOn) return;
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        gain.connect(ctx.destination); osc.connect(gain);
        if (type === 'success') { osc.type = 'triangle'; osc.frequency.setValueAtTime(880, ctx.currentTime); osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1); gain.gain.setValueAtTime(0.15, ctx.currentTime); gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3); osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.3); }
        else if (type === 'error') { osc.type = 'sawtooth'; osc.frequency.setValueAtTime(200, ctx.currentTime); gain.gain.setValueAtTime(0.1, ctx.currentTime); gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4); osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.4); }
        else { osc.type = 'sine'; osc.frequency.setValueAtTime(660, ctx.currentTime); gain.gain.setValueAtTime(0.1, ctx.currentTime); gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.15); osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.15); }
    } catch (_) {}
}
