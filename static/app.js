/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Application Logic
   Organized into sections. All config at the top.
   ═══════════════════════════════════════════════════════════════════════ */

// ═══════════════════════════════════════════════════════════════════════
// 1. CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════

// -- Scoring weights per schema ----------------------------------------
const SCHEMA_WEIGHTS = {
    food_new:    { a: 0.30, b: 0.25, c: 0.20, d: 0.15, e: 0.10 },
    food_expire: { a: 0.20, b: 0.20, c: 0.25, d: 0.20, e: 0.15 },
    item_new:    { a: 0.25, b: 0.35, c: 0.10, d: 0.20, e: 0.10 },
    item_expire: { a: 0.25, b: 0.30, c: 0.10, d: 0.25, e: 0.10 },
};

// -- Criteria labels per schema ---------------------------------------
const CRITERIA_LABELS = {
    food_new:    { a: 'Env. Impact', b: 'Sustainability', c: 'Biodegradable', d: 'Recyclability', e: 'Preservation' },
    food_expire: { a: 'Env. Impact', b: 'Sustainability', c: 'Biodegradable', d: 'Recycling', e: 'Safety & Waste' },
    item_new:    { a: 'Env. Impact', b: 'Sustainability', c: 'Biodegradable', d: 'Recycling', e: 'Social & Innovation' },
    item_expire: { a: 'Env. Impact', b: 'Sustainability', c: 'Biodegradable', d: 'Recycling', e: 'Reuse Potential' },
};

// ═══════════════════════════════════════════════════════════════════════
// 2. UTILITIES — tr() uses I18N loader from static/js/i18n.js
// ═══════════════════════════════════════════════════════════════════════

function tr(key) {
    return (typeof I18N !== 'undefined' && I18N.tr) ? I18N.tr(key) : key;
}

// ═══════════════════════════════════════════════════════════════════════
// 2b. TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════════════

const TOAST_ICONS = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
};

function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.setAttribute('role', 'alert');

    const icon = TOAST_ICONS[type] || TOAST_ICONS.info;
    toast.innerHTML = `
        <span class="toast-icon">${icon}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="dismissToast(this.parentElement)" aria-label="Dismiss">✕</button>
        <div class="toast-progress"></div>
    `;

    container.appendChild(toast);

    // Animate in
    if (typeof gsap !== 'undefined' && gsap.to !== '[function]') {
        try {
            gsap.fromTo(toast, {
                opacity: 0,
                y: -20,
                scale: 0.92,
            }, {
                opacity: 1,
                y: 0,
                scale: 1,
                duration: 0.35,
                ease: 'back.out(1.4)',
                clearProps: 'transform',
            });
        } catch (_) {
            toast.style.opacity = '1';
        }
    } else {
        requestAnimationFrame(() => { toast.style.opacity = '1'; });
    }

    // Auto-dismiss
    toast._dismissTimer = setTimeout(() => dismissToast(toast), duration);

    // Dismiss on tap
    toast.addEventListener('click', (e) => {
        if (e.target.closest('.toast-close')) return;
        dismissToast(toast);
    });

    return toast;
}

function dismissToast(toast, immediate = false) {
    if (toast._dismissed) return;
    toast._dismissed = true;

    clearTimeout(toast._dismissTimer);

    if (typeof gsap !== 'undefined' && gsap.to !== '[function]') {
        try {
            gsap.to(toast, {
                opacity: 0,
                y: -12,
                scale: 0.95,
                duration: immediate ? 0.1 : 0.25,
                ease: 'power2.in',
                onComplete: () => toast.remove(),
            });
        } catch (_) {
            toast.remove();
        }
    } else {
        toast.remove();
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 3. APP STATE
// ═══════════════════════════════════════════════════════════════════════

const state = {
    activeTab: 'home',
    scanMode: 'dispose',
    selectedFile: null,
    selectedFileDataUrl: '',
    currentTipIndex: 0,
    tips: [],
    lang: 'en',
    aiMode: true,
    itemType: 'food',
    itemState: 'new',
    lastScanResult: null,
    currentUser: null,
    userAvatar: '👤',
    records: [],
    spentPoints: 0,
    earnedPoints: 0,
    userKey: null,
    claimedCoupons: [],
    rewards: [],
    clockInterval: null,
    debugMode: false,
    weather: null,
    weatherLoadPromise: null,
    weatherRequestId: 0,
    weatherDetailsOpen: false,
    nearbyRecyclingPoints: [],
    nearbyRecyclingStatus: 'idle',
    nearbyRecyclingSourceUrl: '',
    nearbyRecyclingRequestId: 0,
    recordsDirty: true,
    recordsLoadedFor: '',
    recordsLoadPromise: null,
    recordsLoadPromiseToken: 0,
    recordsLoadToken: 0,
};

const PERF = (typeof window !== 'undefined' && window.RELIFE_PERF) ? window.RELIFE_PERF : { reducedMotion: false, lowEnd: false, motionEnabled: true };
const MOTION_ENABLED = PERF.motionEnabled !== false;
const NEWS_CACHE_KEY = 'RE_LIFE_NEWS_CACHE';
const NEWS_FALLBACK_ITEMS = [
    { title: 'HK expands GREEN@COMMUNITY recycling network', source: 'SCMP', link: '', snippet: '' },
    { title: 'New sorting systems improve plastic recovery', source: 'BBC News', link: '', snippet: '' },
    { title: 'Ocean cleanup projects scale up across Asia', source: 'Reuters', link: '', snippet: '' },
    { title: 'Cities push harder on waste reduction policies', source: 'The Guardian', link: '', snippet: '' },
    { title: 'Fresh recycling habits cut carbon at home', source: 'CNN', link: '', snippet: '' },
];
let tipsSwitchTimer = null;
let tipsRenderToken = 0;

const GSAP_FALLBACK = (() => {
    const noop = () => GSAP_FALLBACK;
    return {
        to: noop,
        from: noop,
        fromTo: noop,
        set: noop,
        killTweensOf: () => {},
        timeline: noop,
    };
})();

const gsap = (typeof window !== 'undefined' && window.gsap && typeof window.gsap.to === 'function')
    ? window.gsap
    : GSAP_FALLBACK;

function readSessionState() {
    return {
        name: safeStorage.get('RE_LIFE_CURRENT_USER'),
        id: safeStorage.get('RE_LIFE_CURRENT_USER_ID'),
        key: safeStorage.get('RE_LIFE_CURRENT_USER_KEY'),
        avatar: safeStorage.get('RE_LIFE_USER_AVATAR'),
    };
}

function persistSessionState(session = {}) {
    const apply = (key, value) => {
        if (value === undefined || value === null || value === '') {
            safeStorage.remove(key);
        } else {
            safeStorage.set(key, value);
        }
    };

    apply('RE_LIFE_CURRENT_USER', session.name);
    apply('RE_LIFE_CURRENT_USER_ID', session.id);
    apply('RE_LIFE_CURRENT_USER_KEY', session.key);
    apply('RE_LIFE_USER_AVATAR', session.avatar);
}

function clearSessionState() {
    persistSessionState({});
}


// ═══════════════════════════════════════════════════════════════════════
// 4. INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
    // Detect login page vs main app
    if (document.querySelector('.login-page')) {
        initLoginPage();
        return;
    }

    // Main app — redirect to login if no session
    const session = readSessionState();
    if (!session.name && !session.id && !session.key) {
        window.location.replace('/login');
        return;
    }

    // Init language from storage
    state.lang = safeStorage.get('RE_LIFE_LANG') || 'en';
    document.documentElement.lang = state.lang === 'zh' ? 'zh-HK' : 'en';
    // Update language indicator immediately
    const langInd = document.getElementById('lang-ind');
    if (langInd) langInd.textContent = state.lang === 'en' ? 'Eng' : '中文';
    // Load i18n then update labels — avoids showing English briefly
    if (typeof I18N !== 'undefined') {
        I18N.load(state.lang).then(() => {
            updateAllLabels();
            updateWeatherUI();
        });
    } else {
        updateAllLabels();
        updateWeatherUI();
    }

    startClock();
    setupDragDrop();
    initNavDrag();
    initTheme();
    setScanModeUI('dispose');
    updateHeaderUI();
    loadHeaderWeather();
    loadTips();

    // Critical: load user before records so we never paint another user's data
    await initAccounts();
    await loadRecords();

    // Non-critical: lazy load in background
    const runBackgroundLoads = () => {
        loadRewards();
        loadFact();
        detectCamera();
    };
    if (typeof window.requestIdleCallback === 'function') {
        try {
            window.requestIdleCallback(runBackgroundLoads, { timeout: 1200 });
        } catch (_) {
            setTimeout(runBackgroundLoads, 500);
        }
    } else {
        setTimeout(runBackgroundLoads, 500);
    }
});

let cameraAvailable = false;

async function detectCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        cameraAvailable = false;
        return;
    }
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        cameraAvailable = devices.some(d => d.kind === 'videoinput');
    } catch (_) {
        cameraAvailable = false;
    }

    // Show gallery link only when camera is NOT available
    const galleryLink = document.getElementById('upload-gallery-link');
    if (galleryLink) {
        galleryLink.style.display = cameraAvailable ? 'none' : 'inline-block';
    }
}

function startClock() {
    const tick = () => {
        const el = document.getElementById('header-time');
        if (el) {
            el.textContent = new Date().toLocaleTimeString('en-US', {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
            });
        }
    };
    tick();
    state.clockInterval = setInterval(tick, 1000);
}

// ═══════════════════════════════════════════════════════════════════════
// 5. NAVIGATION
// ═══════════════════════════════════════════════════════════════════════

function initNavDrag() {
    const navbar = document.querySelector('nav.nav, .app-nav');
    if (!navbar) return;
    const indicator = document.getElementById('nav-indicator');
    const btns = navbar.querySelectorAll('.nav-btn');
    const btnArray = Array.from(btns);
    let isDragging = false;
    let activePointerId = null;
    let pointerStartX = 0;
    let pointerStartY = 0;
    let pendingTab = state.activeTab;
    let suppressNavClickUntil = 0;

    if (indicator) {
        indicator.style.transformOrigin = 'left center';
        indicator.style.transform = 'translate3d(0, 0, 0) scaleX(1)';
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function getIndicatorBox(btn, navRect = navbar.getBoundingClientRect()) {
        const rect = btn.getBoundingClientRect();
        const edge = 5;
        const baseLeft = 5;
        const width = clamp(rect.width - 8, 52, Math.max(52, navRect.width - edge * 2));
        const maxX = Math.max(edge, navRect.width - width - edge);
        const x = clamp(rect.left - navRect.left + (rect.width - width) / 2, edge, maxX) - baseLeft;
        return { x, width, center: rect.left - navRect.left + rect.width / 2, rect };
    }

    function setIndicator(targetX, width, duration, ease) {
        if (!indicator) return;
        if (width) indicator.style.width = `${width}px`;
        if (MOTION_ENABLED) {
            gsap.to(indicator, {
                x: targetX,
                scaleX: 1,
                duration,
                ease,
                overwrite: "auto",
            });
        } else {
            indicator.style.transform = `translate3d(${targetX}px, 0, 0) scaleX(1)`;
        }
    }

    function getTabName(btn) {
        if (!btn) return null;
        return btn.dataset.tab || null;
    }

    // Position indicator under active tab initially
    function snapIndicatorTo(btn) {
        if (!indicator || !btn) return;
        const box = getIndicatorBox(btn);
        setIndicator(box.x, box.width, isDragging ? 0.12 : 0.28, isDragging ? "power2.out" : "power3.out");

        if (!isDragging && MOTION_ENABLED && !PERF.lowEnd) {
            const icon = btn.querySelector('.nav-btn-icon');
            if (icon) {
                gsap.fromTo(icon, { scale: 0.92 }, { scale: 1, duration: 0.24, ease: "power2.out", overwrite: "auto" });
            }
        }
    }

    // Initial snap — ensure indicator is visible
    const activeBtn = navbar.querySelector('.nav-btn.is-active');
    if (activeBtn) {
        // Small delay to ensure DOM is settled
        requestAnimationFrame(() => requestAnimationFrame(() => snapIndicatorTo(activeBtn)));
    }

    function getBestTab(clientX) {
        const nr = navbar.getBoundingClientRect();
        const relX = clientX - nr.left;

        // Find which two buttons the finger is between for smooth interpolation
        let leftBtn = null, rightBtn = null;
        for (let i = 0; i < btnArray.length; i++) {
            const box = getIndicatorBox(btnArray[i], nr);
            if (box.center <= relX) leftBtn = { el: btnArray[i], ...box };
            if (box.center >= relX && !rightBtn) rightBtn = { el: btnArray[i], ...box };
        }

        // Smoothly interpolate indicator position between adjacent buttons
        if (indicator) {
            if (leftBtn && rightBtn && leftBtn.el !== rightBtn.el) {
                const range = rightBtn.center - leftBtn.center;
                const t = range > 0 ? clamp((relX - leftBtn.center) / range, 0, 1) : 0;
                const x = leftBtn.x + (rightBtn.x - leftBtn.x) * t;
                const width = leftBtn.width + (rightBtn.width - leftBtn.width) * t;
                setIndicator(x, width, 0.08, "power1.out");
            } else if (rightBtn) {
                let x = rightBtn.x, width = rightBtn.width;
                if (rightBtn.el === btnArray[0] && clientX < rightBtn.rect.left + rightBtn.rect.width * 0.4) {
                    const t = Math.min(1, (rightBtn.rect.left + rightBtn.rect.width * 0.4 - clientX) / 50);
                    width = rightBtn.width * (1 - t * 0.18);
                    x = 0;
                }
                setIndicator(x, width, 0.1, "power2.out");
            } else if (leftBtn) {
                let x = leftBtn.x, width = leftBtn.width;
                if (leftBtn.el === btnArray[btnArray.length - 1] && clientX > leftBtn.rect.right - leftBtn.rect.width * 0.4) {
                    const t = Math.min(1, (clientX - (leftBtn.rect.right - leftBtn.rect.width * 0.4)) / 50);
                    width = leftBtn.width * (1 - t * 0.18);
                    x = nr.width - width - 10;
                }
                setIndicator(x, width, 0.1, "power2.out");
            }
        }

        // Find best match for tab switching
        let best = null, minDist = Infinity;
        btns.forEach(btn => {
            const r = btn.getBoundingClientRect();
            const dist = Math.abs(clientX - (r.left + r.width / 2));
            if (dist < minDist) { minDist = dist; best = btn; }
        });
        if (best) {
            const tabName = getTabName(best);
            if (tabName) {
                pendingTab = tabName;
                return tabName;
            }
        }
        return pendingTab;
    }

    navbar.addEventListener('click', e => {
        if (Date.now() < suppressNavClickUntil) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    navbar.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        activePointerId = e.pointerId;
        pointerStartX = e.clientX;
        pointerStartY = e.clientY;
        isDragging = true;
        pendingTab = state.activeTab;
        navbar.setPointerCapture(e.pointerId);
        getBestTab(e.clientX);
    });
    const updateDrag = e => {
        if (activePointerId === null || e.pointerId !== activePointerId) return;
        const dx = Math.abs(e.clientX - pointerStartX);
        const dy = Math.abs(e.clientY - pointerStartY);
        if (!navbar.classList.contains('nav-is-dragging') && (dx > 6 || dy > 6)) {
            navbar.classList.add('nav-is-dragging');
        }
        if (navbar.classList.contains('nav-is-dragging')) {
            isDragging = true;
            getBestTab(e.clientX);
        }
    };
    navbar.addEventListener('pointermove', updateDrag);
    document.addEventListener('pointermove', updateDrag);
    const stop = e => {
        if (activePointerId === null || e.pointerId !== activePointerId) return;
        const hadDrag = navbar.classList.contains('nav-is-dragging');
        isDragging = false;
        activePointerId = null;
        navbar.classList.remove('nav-is-dragging');
        try { navbar.releasePointerCapture(e.pointerId); } catch {}
        if (indicator) {
            gsap.killTweensOf(indicator);
            indicator.style.transform = '';
        }

        const active = navbar.querySelector('.nav-btn.is-active');
        if (active) snapIndicatorTo(active);

        const targetTab = pendingTab || getBestTab(e.clientX);
        if (targetTab && state.activeTab !== targetTab) {
            navigateTo(targetTab);
        }
        if (hadDrag) {
            suppressNavClickUntil = Date.now() + 350;
        }
    };
    navbar.addEventListener('pointerup', stop);
    navbar.addEventListener('pointercancel', stop);
    document.addEventListener('pointerup', stop);
    document.addEventListener('pointercancel', stop);

    // Update indicator when tab changes via click too
    window._snapNavIndicator = () => {
        const a = navbar.querySelector('.nav-btn.is-active');
        if (a) snapIndicatorTo(a);
    };
}

// ═══════════════════════════════════════════════════════════════════════
// 6. TAB NAVIGATION
// ═══════════════════════════════════════════════════════════════════════

let _tabTween = null;

const TAB_ORDER = ['home', 'record', 'rewards', 'more'];

function getTabDirection(nextName) {
    const currentIndex = TAB_ORDER.indexOf(state.activeTab);
    const nextIndex = TAB_ORDER.indexOf(nextName);
    if (currentIndex === -1 || nextIndex === -1 || currentIndex === nextIndex) return 1;
    return nextIndex > currentIndex ? 1 : -1;
}

function runTabSideEffects(name) {
    if (name === 'record') loadRecords();
    if (name === 'rewards') {
        renderRewards();
        const balance = Math.max(0, (state.earnedPoints || 0) - (state.spentPoints || 0));
        const ptsEl = document.getElementById('rew-pts');
        if (ptsEl) {
            const cur = parseInt(ptsEl.textContent) || 0;
            animateNumber('rew-pts', cur, balance, 1000);
        }
    }
}

function resetTabVisuals(tab) {
    if (!tab) return;
    gsap.killTweensOf(tab);
    gsap.killTweensOf(tab.children);
    gsap.set([tab, ...tab.children], { clearProps: "opacity,visibility,transform" });
}

function cleanupTabTween(currentTab, nextTab) {
    if (currentTab) currentTab.classList.remove('active', 'tab-exiting');
    resetTabVisuals(currentTab);
    resetTabVisuals(nextTab);
    if (nextTab) {
        nextTab.style.opacity = '';
        nextTab.style.visibility = '';
    }
    _tabTween = null;
}

function navigateTo(name) {
    if (_tabTween) { _tabTween.kill(); _tabTween = null; }
    document.querySelectorAll('.tab-exiting').forEach(tab => {
        tab.classList.remove('active', 'tab-exiting');
        resetTabVisuals(tab);
    });

    const direction = getTabDirection(name);
    const currentTab = document.querySelector(`#tab-${state.activeTab}.active`) || document.querySelector('.tab.active');
    const nextTab = document.getElementById(`tab-${name}`);
    if (!nextTab) return;
    if (currentTab === nextTab) return;

    state.activeTab = name;
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('is-active'));
    const nav = document.getElementById(`nav-${name}`);
    if (nav) { nav.classList.add('is-active'); if (window._snapNavIndicator) window._snapNavIndicator(); }

    document.querySelectorAll('.tab').forEach(tab => {
        if (tab !== currentTab && tab !== nextTab) {
            tab.classList.remove('active', 'tab-exiting');
            resetTabVisuals(tab);
        }
    });
    nextTab.classList.add('active');
    resetTabVisuals(nextTab);
    runTabSideEffects(name);

    if (!MOTION_ENABLED) {
        if (currentTab) currentTab.classList.remove('active', 'tab-exiting');
        resetTabVisuals(currentTab);
        resetTabVisuals(nextTab);
        return;
    }

    const isNarrowScreen = window.matchMedia('(max-width: 760px)').matches;
    const distance = isNarrowScreen ? 14 : (PERF.lowEnd ? 12 : 24);
    const duration = 0.32;
    const nextChildren = nextTab.querySelectorAll(':scope > *');
    nextTab.scrollTop = 0;
    if (currentTab) currentTab.classList.add('tab-exiting');

    _tabTween = gsap.timeline({
        defaults: { ease: "power3.out", overwrite: "auto" },
        onComplete: () => cleanupTabTween(currentTab, nextTab),
        onInterrupt: () => cleanupTabTween(currentTab, nextTab),
    });

    if (currentTab) {
        _tabTween.to(currentTab, {
            opacity: 0,
            x: -distance * direction,
            scale: 0.97,
            duration: 0.18,
            ease: "power2.in",
        }, 0);
    }

    _tabTween.fromTo(nextTab, {
        opacity: 0,
        x: distance * direction,
        scale: 0.97,
    }, {
        opacity: 1,
        x: 0,
        scale: 1,
        duration,
        ease: "power3.out",
        clearProps: "transform",
    }, currentTab ? 0.08 : 0);

    // Children stagger - apply on all screens, smaller stagger on mobile
    if (!PERF.lowEnd && nextChildren.length) {
        _tabTween.fromTo(nextChildren, {
            opacity: 0,
            y: isNarrowScreen ? 6 : 10,
        }, {
            opacity: 1,
            y: 0,
            duration: isNarrowScreen ? 0.2 : 0.28,
            stagger: isNarrowScreen ? 0.02 : 0.035,
            ease: "power2.out",
        }, currentTab ? 0.14 : 0.08);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 7. SCAN MODE
// ═══════════════════════════════════════════════════════════════════════

function startScanningMode(mode) {
    state.scanMode = mode;
    // Dispose defaults: food + about to expire; Purchase defaults: food + new
    state.itemType = mode === 'dispose' ? 'food' : 'food';
    state.itemState = mode === 'dispose' ? 'expire' : 'new';
    navigateTo('home');
    setScanModeUI(mode);
}

function setScanModeUI(mode) {
    state.scanMode = mode;
    document.querySelectorAll('.scan-btn').forEach(b => b.classList.remove('scan-btn--active'));
    const active = document.querySelector(`.scan-btn--${mode}`);
    if (active) {
        active.classList.add('scan-btn--active');
        if (MOTION_ENABLED) {
            gsap.fromTo(active, { scale: 0.92 }, { scale: 1.04, duration: 0.35, ease: "elastic.out(1, 0.4)" });
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 8. FILE UPLOAD
// ═══════════════════════════════════════════════════════════════════════

function triggerUpload() {
    document.getElementById('file-input').click();
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) processFile(file);
}

function setupDragDrop() {
    const zone = document.getElementById('upload-zone');
    if (!zone) return;
    zone.addEventListener('dragover', e => {
        e.preventDefault();
        if (!zone.classList.contains('drag-over')) {
            zone.classList.add('drag-over');
            if (MOTION_ENABLED) {
                gsap.to(zone, { scale: 1.02, duration: 0.2, ease: "power2.out" });
            }
        }
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) processFile(file);
    });
}

function processFile(file) {
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file.');
        return;
    }
    state.selectedFile = file;
    const reader = new FileReader();
    reader.onload = () => {
        state.selectedFileDataUrl = reader.result;
        showPreview(state.selectedFileDataUrl);
        doScan(); // auto-scan after file selection
    };
    reader.readAsDataURL(file);
}

function showPreview(dataUrl) {
    const zone = document.getElementById('upload-zone');
    const preview = document.getElementById('upload-preview');
    const icon = zone.querySelector('.upload-zone-icon');
    const text = zone.querySelector('.upload-zone-text');
    const sub = zone.querySelector('.upload-zone-sub');

    // Hide the placeholder icon + text
    if (icon) icon.style.display = 'none';
    if (text) text.style.display = 'none';
    if (sub) sub.style.display = 'none';

    // Show the image in the upload zone
    document.getElementById('upload-preview-img').src = dataUrl;
    preview.classList.add('is-shown');
    zone.classList.add('has-image');
    if (MOTION_ENABLED) {
        gsap.from(preview, { scale: 0.9, opacity: 0, duration: 0.35, ease: "back.out(1.4)" });
    }
}

function clearPreview() {
    state.selectedFile = null;
    state.selectedFileDataUrl = '';
    if (typeof resetNearbyRecyclingUI === 'function') {
        resetNearbyRecyclingUI();
    }
    const zone = document.getElementById('upload-zone');
    const preview = document.getElementById('upload-preview');
    const icon = zone.querySelector('.upload-zone-icon');
    const text = zone.querySelector('.upload-zone-text');
    const sub = zone.querySelector('.upload-zone-sub');

    // Restore the placeholder
    if (icon) icon.style.display = '';
    if (text) text.style.display = '';
    if (sub) sub.style.display = '';

    preview.classList.remove('is-shown');
    zone.classList.remove('has-image');
    document.getElementById('file-input').value = '';
}


// ═══════════════════════════════════════════════════════════════════════
// 9. CAMERA
// ═══════════════════════════════════════════════════════════════════════
function zoneTap() {
    if (state.selectedFile) return; // preview is showing, ignore tap
    if (cameraAvailable) {
        openCamera();
    } else {
        triggerUpload();
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 9. SCAN (Mock + Gemini AI)
// ═══════════════════════════════════════════════════════════════════════

async function doScan() {
    if (!state.selectedFile) return;

    const status = document.getElementById('scan-status');
    status.classList.add('is-shown');
    if (MOTION_ENABLED) {
        gsap.fromTo(status, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.3 });
    }
    document.getElementById('scan-result').classList.add('hidden');

    try {
        const fd = new FormData();
        fd.append('file', state.selectedFile);
        fd.append('mode', state.scanMode);
        fd.append('item_type', state.itemType);
        fd.append('item_state', state.itemState);
        fd.append('lang', state.lang);
        if (state.debugMode) fd.append('debug', 'true');

        const res = await fetch('/api/scan/ai', { method: 'POST', body: fd });
        const data = await res.json();

        data.mode = data.mode || state.scanMode;
        if (state.selectedFileDataUrl) {
            data.image_url = state.selectedFileDataUrl;
            data.photoUrl = state.selectedFileDataUrl;
            data.image_cached_locally = true;
        }

        // Enrich if backend didn't fully score
        if (data.overall_score === undefined) {
            data.weighted_scores = data.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 };
            data.schema_id = `${state.itemType}_${state.itemState}`;
            data.overall_score = calcWeighted(data.weighted_scores, data.schema_id);
            const g = getGrade(data.overall_score);
            data.grade = g.grade;
            data.grade_advice = g.advice;
            data.grade_color = g.color;
            data.criteria_labels = CRITERIA_LABELS[data.schema_id];
        }

        showScanResult(data);
        playBeep('success');
    } catch (err) {
        console.error('Scan error:', err);
        if (typeof resetNearbyRecyclingUI === 'function') {
            resetNearbyRecyclingUI();
        }
        const msg = (err.message || String(err));
        document.getElementById('scan-result').classList.remove('hidden');
        const imgContainer = document.getElementById('result-img');
        imgContainer.innerHTML = '';
        imgContainer.textContent = '📦';
        document.getElementById('result-name').textContent = 'Scan Error';
        document.getElementById('result-desc').textContent = msg;
        document.getElementById('result-desc').classList.remove('hidden');
        document.getElementById('result-brand').textContent = '';
        document.getElementById('result-brand').classList.add('hidden');
        document.getElementById('result-ratings').classList.add('hidden');
        document.getElementById('result-alt').classList.add('hidden');
        document.getElementById('weighted-section').classList.add('hidden');
        document.getElementById('weighted-detail').classList.remove('is-open');
        document.getElementById('disposal-guide').classList.add('hidden');
        document.getElementById('lbl-prove-swap').classList.add('hidden');
        document.getElementById('gemini-error').textContent = '❌ ' + msg;
        document.getElementById('gemini-error').style.display = 'block';
        playBeep('error');
    } finally {
        document.getElementById('scan-status').classList.remove('is-shown');
    }
}

function showScanResult(item) {
    const result = document.getElementById('scan-result');
    result.classList.remove('hidden');
    // GSAP entrance animation
    if (MOTION_ENABLED) {
        gsap.fromTo(result, { opacity: 0, y: 20, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.4, ease: "power2.out" });
    }

    // Image
    const imgContainer = document.getElementById('result-img');
    imgContainer.textContent = item.mode === 'purchase' ? '🥛' : '🗑️';
    if (item.image_url) {
        const img = document.createElement('img');
        img.src = item.image_url;
        img.decoding = 'async';
        img.loading = 'eager';
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:12px';
        imgContainer.textContent = '';
        imgContainer.appendChild(img);
    }

    const brandEl = document.getElementById('result-brand');
    const descEl = document.getElementById('result-desc');
    const ratingsEl = document.getElementById('result-ratings');
    const alt = document.getElementById('result-alt');
    const weightedSection = document.getElementById('weighted-section');
    const weightedDetail = document.getElementById('weighted-detail');
    const guide = document.getElementById('disposal-guide');
    const proveBtn = document.getElementById('lbl-prove-swap');
    if (typeof resetNearbyRecyclingUI === 'function') {
        resetNearbyRecyclingUI();
    }

    // Basic info
    document.getElementById('result-name').textContent = item.name || item.waste_label || item.category || '';
    if (brandEl) {
        const brandText = item.brand || item.category || '';
        brandEl.textContent = brandText;
        brandEl.classList.toggle('hidden', !brandText);
    }
    if (descEl) {
        const summaryText = item.text || item.description || item.disposal_guide || '';
        descEl.textContent = summaryText;
        descEl.classList.toggle('hidden', !summaryText);
    }

    // Reset Add to Record button for new scan
    const addBtn = document.getElementById('lbl-add-record');
    if (addBtn) {
        addBtn.textContent = 'Add to Record';
        addBtn.disabled = false;
        addBtn.style.opacity = '';
    }

    // AI error
    const errEl = document.getElementById('gemini-error');
    if (item.ai_error || item.gemini_error) {
        errEl.textContent = '⚠️ ' + (item.ai_error || item.gemini_error);
        errEl.style.display = 'block';
    } else {
        errEl.style.display = 'none';
    }

    if (ratingsEl) ratingsEl.classList.remove('hidden');

    // Star ratings
    renderStars('result-eco-stars', item.eco_rate);
    renderStars('result-recycle-stars', item.recycle_rate);

    // Alternative product (purchase mode only)
    const isPurchase = item.mode === 'purchase';
    if (item.alternative && isPurchase) {
        alt.classList.remove('hidden');
        document.getElementById('alt-name').textContent = item.alternative.name;
        renderStars('alt-eco-stars', item.alternative.eco_rate);
        renderStars('alt-recycle-stars', item.alternative.recycle_rate);
        if (MOTION_ENABLED) {
            gsap.from(alt, { opacity: 0, y: 12, duration: 0.35, ease: "power2.out" });
        }
    } else {
        alt.classList.add('hidden');
    }

    // Swap proof button — only in purchase mode when there is a swap path.
    if (proveBtn) {
        if (isPurchase && (item.alternative || item.swap_pending)) {
            proveBtn.classList.remove('hidden');
            proveBtn.textContent = item.alternative
                ? '♻️ Swap & Prove You Swapped → Earn +50 Pts'
                : '📸 Prove Your Swap → Earn +50 Pts';
            proveBtn.style.background = '';
            proveBtn.disabled = false;
        } else {
            proveBtn.classList.add('hidden');
        }
    }

    // Weighted score breakdown
    const schemaId = item.schema_id || 'food_new';
    if (weightedSection) weightedSection.classList.remove('hidden');
    if (weightedDetail) weightedDetail.classList.add('is-open');
    const overall = item.overall_score ||
        calcWeighted(item.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 }, schemaId);
    const grade = item.grade ? { grade: item.grade, color: item.grade_color } : getGrade(overall);

    document.getElementById('ov-score').textContent = overall;
    const barFill = document.getElementById('ov-bar-fill');
    if (barFill) {
        barFill.style.transformOrigin = 'left center';
        if (MOTION_ENABLED) {
            gsap.fromTo(barFill, { scaleX: 0 }, { scaleX: overall / 100, duration: 0.8, ease: "power3.out" });
        }
        barFill.style.backgroundColor = grade.color;
        barFill.style.width = `${overall}%`;
    }

    // Animate circular ring fill
    const ringFill = document.getElementById('score-ring-fill');
    if (ringFill) {
        const circumference = 326.73; // 2 * π * 52
        const offset = circumference - (overall / 100) * circumference;
        if (MOTION_ENABLED && typeof gsap !== 'undefined' && gsap.to) {
            gsap.fromTo(ringFill,
                { strokeDashoffset: circumference, stroke: grade.color },
                { strokeDashoffset: offset, stroke: grade.color, duration: 0.9, ease: "power3.out" }
            );
        } else {
            ringFill.style.strokeDashoffset = offset;
            ringFill.style.stroke = grade.color;
        }
    }

    document.getElementById('grade-tag').textContent = grade.grade;
    document.getElementById('grade-tag').style.background = grade.color;
    document.getElementById('grade-advice').textContent = item.grade_advice || '';

    // Criteria detail bars
    const labels = item.criteria_labels || CRITERIA_LABELS[schemaId] || CRITERIA_LABELS.food_new;
    const scores = item.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 };
    const weights = SCHEMA_WEIGHTS[schemaId] || SCHEMA_WEIGHTS.food_new;
    if (weightedDetail) weightedDetail.innerHTML = '';

    if (weightedDetail) {
        for (const k of ['a', 'b', 'c', 'd', 'e']) {
            const v = scores[k] || 50;
            const w = Math.round(weights[k] * 100);
            const barColor = getBarColor(v);
            weightedDetail.innerHTML += `
                <div class="criterion-row" data-key="${k}">
                    <div class="criterion-header">
                        <span class="criterion-name">${labels[k]} (${w}%)</span>
                        <span class="criterion-score">${v}/100</span>
                    </div>
                    <div class="criterion-bar" data-key="${k}">
                        <div class="criterion-bar-fill is-animated" style="width:${v}%;background:${barColor}" data-key="${k}"></div>
                    </div>
                </div>`;
        }
    }

    // Disposal guide
    const dispInfo = item.disposal_info;
    if (dispInfo || item.disposal_guide) {
        const reuseTip = item.reuse_tip || item.reuse || getReuseTip(item);
        item.reuse_tip = reuseTip;
        guide.classList.remove('hidden');
        document.getElementById('disp-material').textContent = dispInfo?.type || '';
        document.getElementById('disp-method').textContent = dispInfo?.method || '';
        document.getElementById('disp-location').textContent = dispInfo?.location || '';
        document.getElementById('disp-reuse').textContent = reuseTip;
        document.getElementById('disp-guide').textContent = item.disposal_guide || '';
        document.getElementById('disp-prec').textContent = item.precaution || '';
    } else {
        guide.classList.add('hidden');
    }

    state.lastScanResult = item;
    if (guide && !guide.classList.contains('hidden') && typeof loadNearbyRecyclingPointsForScan === 'function') {
        loadNearbyRecyclingPointsForScan(item);
    }
}

function addScanToRecord() {
    if (!state.lastScanResult) return;

    const record = { ...state.lastScanResult };
    delete record.disposal_info;
    delete record.criteria_labels;

    if (record.overall_score === undefined) {
        record.overall_score = calcWeighted(
            record.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 },
            record.schema_id || 'food_new'
        );
    }

    record.userId = state.userId || null;
    record.userName = state.currentUser || null;

    // Disable add button
    const addBtn = document.getElementById('lbl-add-record');
    if (addBtn) {
        addBtn.textContent = '✓ Added to Record';
        addBtn.disabled = true;
        addBtn.style.opacity = '0.6';
    }

    // Save to backend storage
    FB.addItem(record)
        .then(({ id, image_url }) => {
            const savedImageUrl = image_url || record.image_url || record.photoUrl || '';
            if (id !== null && id !== undefined) {
                upsertRecordCache({
                    ...record,
                    id,
                    mode: record.mode || record.status || 'dispose',
                    status: record.mode || record.status || 'dispose',
                    image_url: savedImageUrl,
                    photoUrl: savedImageUrl,
                    disposal_guide: record.disposal_guide || record.dealtWithMethod || '',
                    dealtWithMethod: record.dealtWithMethod || record.disposal_guide || '',
                    userId: state.userId || null,
                    userName: state.currentUser || null,
                });
            } else {
                invalidateRecordsCache();
            }
            playBeep('success');
        })
        .catch(err => {
            const message = err?.message || String(err || 'Unknown error');
            console.error('Failed to save item:', message, err);
            if (addBtn) {
                addBtn.textContent = tr('addToRecord');
                addBtn.disabled = false;
                addBtn.style.opacity = '';
            }
            playBeep('error');
            showToast(`Failed to save record: ${message}`, 'error', 5000);
        });
}

function getReuseTip(item = {}) {
    const category = String(item.category || item.material || item.name || '').toLowerCase();
    if (category.includes('food') || category.includes('organic')) {
        return "If it is still safe, turn leftovers into tomorrow's soup base, lunch-box remix, or share-it-now snack; otherwise compost it.";
    }
    if (category.includes('glass') || category.includes('bottle') || category.includes('jar')) {
        return 'Give it a second career: spice jar, cutting-root vase, desk coin catcher, then recycle it clean.';
    }
    if (category.includes('paper') || category.includes('cardboard')) {
        return 'Fold it into drawer dividers, gift tags, seed-starting trays, or a messy-desk scratch pad before recycling.';
    }
    if (category.includes('elect') || category.includes('device') || category.includes('ewaste')) {
        return 'Try one rescue lap: repair cafe, school maker box, parts donor, or certified e-waste handoff.';
    }
    return 'Run a 24-hour second-life challenge: refill it, loan it, turn it into storage, then choose recycling/disposal.';
}

function swapAlternative() {
    if (!state.lastScanResult || !state.lastScanResult.alternative) return;
    const alt = state.lastScanResult.alternative;
    state.lastScanResult.name = alt.name;
    state.lastScanResult.eco_rate = alt.eco_rate;
    state.lastScanResult.recycle_rate = alt.recycle_rate;
    state.lastScanResult.alternative = null;
    state.lastScanResult.swap_pending = true;
    state.lastScanResult.description = 'Swapped to eco-friendly alternative.';
    showScanResult(state.lastScanResult);
    playBeep('beep');
}

function completeSwapFlow() {
    if (!state.lastScanResult) return;
    if (state.lastScanResult.alternative) {
        swapAlternative();
    }
    triggerSwapProof();
}

function triggerSwapProof() {
    document.getElementById('swap-proof-input').click();
}

async function handleSwapProof(e) {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';

    // Only award points if item was added to record first
    const addBtn = document.getElementById('lbl-add-record');
    if (!addBtn || !addBtn.disabled) {
        const btn = document.getElementById('lbl-prove-swap');
        if (btn) btn.textContent = '⚠️ Add to Record first';
        setTimeout(() => {
            if (btn) btn.textContent = state.lastScanResult?.alternative
                ? '♻️ Swap & Prove You Swapped → Earn +50 Pts'
                : '📸 Prove Your Swap → Earn +50 Pts';
        }, 2000);
        return;
    }

    // Simulated proof — any photo earns points
    const points = 50;
    state.earnedPoints = (state.earnedPoints || 0) + points;
    saveUserData();

    const btn = document.getElementById('lbl-prove-swap');
    if (btn) {
        btn.textContent = '✅ +' + points + ' Points Earned!';
        btn.style.background = 'var(--color-emerald-700)';
        btn.disabled = true;
        if (MOTION_ENABLED) {
            gsap.fromTo(btn, { scale: 1 }, { scale: 1.1, duration: 0.15, yoyo: true, repeat: 1, ease: "power2.out" });
        }
    }
    // Refresh points display
    if (state.activeTab === 'rewards') renderRewards();
    playBeep('success');
}

function resetScan() {
    const result = document.getElementById('scan-result');
    if (!result.classList.contains('hidden')) {
        if (MOTION_ENABLED) {
            gsap.to(result, { opacity: 0, scale: 0.95, y: -10, duration: 0.25, ease: "power2.in", onComplete: () => {
                result.classList.add('hidden');
                result.style.opacity = ''; result.style.transform = '';
            }});
        } else {
            result.classList.add('hidden');
            result.style.opacity = '';
            result.style.transform = '';
        }
    } else {
        result.classList.add('hidden');
    }
    clearPreview();
    document.getElementById('weighted-detail').classList.remove('is-open');
    state.lastScanResult = null;
    if (typeof resetNearbyRecyclingUI === 'function') {
        resetNearbyRecyclingUI();
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 11. TIPS & FACTS
// ═══════════════════════════════════════════════════════════════════════

async function loadTips() {
    const cachedTips = readCachedNews();
    if (cachedTips.length) {
        applyTips(cachedTips);
    } else {
        applyTips(NEWS_FALLBACK_ITEMS);
    }

    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller ? window.setTimeout(() => controller.abort(), 4500) : null;
    try {
        const res = await fetch('/api/news', {
            headers: { Accept: 'application/json' },
            ...(controller ? { signal: controller.signal } : {}),
        });
        if (!res.ok) throw new Error(`news ${res.status}`);
        const news = await res.json();
        const items = normalizeNewsItems(news);
        if (items.length) {
            applyTips(items);
            writeCachedNews(items);
        }
    } catch (e) {
        if (!e || e.name !== 'AbortError') {
            console.warn('Green news fallback used:', e);
        }
    } finally {
        if (timeoutId) clearTimeout(timeoutId);
    }
}

function readCachedNews() {
    try {
        const raw = safeStorage.get(NEWS_CACHE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return normalizeNewsItems(parsed);
    } catch (_) {
        return [];
    }
}

function writeCachedNews(items) {
    try {
        safeStorage.set(NEWS_CACHE_KEY, JSON.stringify(items.slice(0, 8)));
    } catch (_) {}
}

function normalizeNewsItems(news) {
    if (!Array.isArray(news)) return [];
    return news.map(n => ({
        title: String(n?.title || '').trim(),
        source: String(n?.source || '').trim() || 'Google News',
        snippet: String(n?.snippet || '').trim(),
        link: String(n?.link || '').trim(),
    })).filter(item => item.title);
}

function applyTips(items) {
    state.tips = items.length ? items : NEWS_FALLBACK_ITEMS.slice();
    renderTipsDots();
    showTip(0);
}

function renderTipsDots() {
    document.getElementById('tips-dots').innerHTML = state.tips
        .map((_, i) =>
            `<span class="tips-dot ${i === state.currentTipIndex ? 'is-active' : ''}" onclick="showTip(${i})"></span>`
        )
        .join('');
}

function showTip(index) {
    state.currentTipIndex = index;
    const tip = state.tips[index];
    if (!tip) return;
    const renderToken = ++tipsRenderToken;
    const titleEl = document.getElementById('tips-title');
    const snippetEl = document.getElementById('tips-snippet');
    if (titleEl) titleEl.classList.add('is-switching');
    if (snippetEl) snippetEl.classList.add('is-switching');
    if (tipsSwitchTimer) clearTimeout(tipsSwitchTimer);
    tipsSwitchTimer = setTimeout(() => {
        if (renderToken !== tipsRenderToken) return;
        if (titleEl) {
            if (tip.link) {
                titleEl.innerHTML = `<a href="${esc(tip.link)}" target="_blank" style="color:inherit;text-decoration:underline">${esc(tip.title)}</a>`;
            } else {
                titleEl.textContent = tip.title;
            }
        }
        if (snippetEl) snippetEl.textContent = tip.snippet;
        if (titleEl) titleEl.classList.remove('is-switching');
        if (snippetEl) snippetEl.classList.remove('is-switching');
    }, 250);
    document.getElementById('tips-source').textContent = tip.source;
    document.querySelectorAll('.tips-dot').forEach((d, i) =>
        d.classList.toggle('is-active', i === index)
    );
}

function nextTip() {
    showTip((state.currentTipIndex + 1) % state.tips.length);
}

async function loadFact() {
    try {
        const res = await fetch('/api/fact');
        const data = await res.json();
        document.getElementById('fact-text').textContent = data.fact;
    } catch (_) {
        /* offline — use default fact from HTML */
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 13. REWARDS
// ═══════════════════════════════════════════════════════════════════════

async function loadRewards() {
    try {
        const res = await fetch('/api/rewards');
        state.rewards = await res.json();
    } catch (e) {
        console.error('Failed to load rewards:', e);
    }
}

function renderRewards() {
    // Points come only from proving swaps, not from adding records
    const balance = Math.max(0, (state.earnedPoints || 0) - (state.spentPoints || 0));
    const oldPoints = parseInt(document.getElementById('rew-pts').textContent) || 0;
    animateNumber('rew-pts', oldPoints, balance, 1000);

    // Shortcut
    document.getElementById('rew-shortcut').classList.toggle('is-shown', state.claimedCoupons.length > 0);

    // Catalogue
    const catalogue = document.getElementById('rew-catalogue');

    if (!state.rewards.length) {
        catalogue.innerHTML = `
            <div class="empty-state empty-state--rewards">
                <div class="empty-state-icon">
                    <svg class="empty-state-svg" viewBox="0 0 120 120" fill="none">
                        <rect x="10" y="20" width="100" height="80" rx="16" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" fill="none" opacity="0.25"/>
                        <circle cx="38" cy="45" r="8" fill="currentColor" opacity="0.08"/>
                        <circle cx="60" cy="45" r="8" fill="currentColor" opacity="0.08"/>
                        <circle cx="82" cy="45" r="8" fill="currentColor" opacity="0.08"/>
                        <rect x="30" y="62" width="60" height="6" rx="3" fill="currentColor" opacity="0.06"/>
                        <rect x="35" y="72" width="50" height="4" rx="2" fill="currentColor" opacity="0.04"/>
                        <path d="M60 8v6M50 10l4 3M70 10l-4 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.15"/>
                    </svg>
                </div>
                <div class="empty-state-text">${tr('noRewards')}</div>
                <div class="empty-state-hint">${tr('noRewardsHint')}</div>
            </div>`;
    } else {
        catalogue.innerHTML = state.rewards.map(rw => {
        const canBuy = balance >= rw.cost;
        return `
        <div class="rewards-item">
            <div class="rewards-item-image">${rw.image}</div>
            <div class="rewards-item-info">
                <span class="rewards-item-provider">${rw.provider}</span>
                <div class="rewards-item-title">${rw.title}</div>
                <div class="rewards-item-desc">${rw.description}</div>
            </div>
            <div class="rewards-item-right">
                <div class="rewards-item-cost">🪙 ${rw.cost}</div>
                <button
                    class="rewards-item-btn ${canBuy ? 'rewards-item-btn--can-buy' : 'rewards-item-btn--cannot-buy'}"
                    ${canBuy ? `onclick="redeemReward('${rw.id}')"` : 'disabled'}
                >${tr('redeem')}</button>
            </div>
        </div>`;
    }).join('');
    } // end else

    // GSAP staggered entrance for rewards
    const items = document.querySelectorAll('#rew-catalogue .rewards-item');
    if (MOTION_ENABLED && items.length) {
        const animItems = Array.from(items).slice(0, 8);
        gsap.fromTo(animItems,
            { opacity: 0, y: 16 },
            { opacity: 1, y: 0, duration: 0.35, stagger: 0.05, ease: "power2.out" }
        );
    }

    // Claimed coupons grid
    const grid = document.getElementById('rew-coupon-grid');
    if (!grid) return;
    if (!state.claimedCoupons.length) {
        grid.innerHTML = `
            <div class="empty-state empty-state--rewards" style="grid-column:1/-1;padding:24px 12px">
                <div class="empty-state-text" style="font-size:12px">${tr('noCoupons')}</div>
                <div class="empty-state-hint" style="font-size:10px">${tr('noCouponsHint')}</div>
            </div>`;
    } else {
        grid.innerHTML = state.claimedCoupons.map(c => `
            <button onclick="showCouponTicket('${c.code}')" class="rewards-coupon">
                <span style="font-size:20px">${c.image}</span>
                <div style="min-width:0">
                    <div style="font-weight:700;font-size:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${c.title}</div>
                    <div style="font-size:8px;color:var(--color-gray-400);font-family:monospace">${c.code}</div>
                </div>
            </button>
        `).join('');
    }
}

function redeemReward(rewardId) {
    const balance = Math.max(0, (state.earnedPoints || 0) - (state.spentPoints || 0));
    const reward = state.rewards.find(r => r.id === rewardId);

    if (!reward || balance < reward.cost) {
        showRewardAlert(tr('insufficientPoints'));
        playBeep('error');
        return;
    }

    fetch('/api/rewards/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reward_id: rewardId }),
    })
        .then(r => r.json())
        .then(data => {
            if (!data.ok) return;
            state.spentPoints += reward.cost;
            state.claimedCoupons.unshift({
                ...reward,
                code: data.coupon.code,
                claimedDate: 'Just now',
                expiry: 'Valid 30 days',
            });
            showCouponTicket(data.coupon.code);
            renderRewards();
            saveUserData();
            playBeep('success');
        });
}

function showRewardAlert(msg) {
    const el = document.getElementById('rew-alert');
    el.textContent = '⚠️ ' + msg;
    el.classList.add('is-shown');
    setTimeout(() => el.classList.remove('is-shown'), 2500);
}


// ═══════════════════════════════════════════════════════════════════════
// 14. MODALS
// ═══════════════════════════════════════════════════════════════════════

function showAlert(title, body, icon) {
    document.getElementById('modal-icon').textContent = icon || '⚠️';
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').textContent = body;
    document.getElementById('modal-actions').innerHTML =
        `<button class="btn btn--primary btn--full" onclick="closeModal()">${tr('closeBtn')}</button>`;
    const overlay = document.getElementById('modal-overlay');
    overlay.classList.add('is-shown');
    const modal = overlay.querySelector('.modal');
    if (modal && MOTION_ENABLED) gsap.fromTo(modal, { scale: 0.85, opacity: 0, y: 16 }, { scale: 1, opacity: 1, y: 0, duration: 0.35, ease: "back.out(1.4)" });
}

function showConfirm(msg, onConfirm) {
    document.getElementById('modal-icon').textContent = '❓';
    document.getElementById('modal-title').textContent = tr('confirmBtn');
    document.getElementById('modal-body').textContent = msg;
    document.getElementById('modal-actions').innerHTML =
        `<button class="btn btn--outline" onclick="closeModal()">${tr('cancelBtn')}</button>
         <button class="btn btn--primary" id="modal-confirm-btn">${tr('confirmBtn')}</button>`;
    document.getElementById('modal-overlay').classList.add('is-shown');
    document.getElementById('modal-confirm-btn').onclick = () => {
        closeModal();
        onConfirm();
    };
}

function showCouponTicket(code) {
    const coupon = state.claimedCoupons.find(c => c.code === code);
    if (!coupon) return;
    document.getElementById('modal-icon').textContent = '🎫';
    document.getElementById('modal-title').textContent = tr('couponClaimed');
    document.getElementById('modal-body').innerHTML = `
        <div class="coupon-code">${coupon.code}</div>
        <div class="coupon-expiry">${coupon.expiry}</div>
        <div style="margin-top:8px;font-size:11px">${coupon.title}</div>`;
    document.getElementById('modal-actions').innerHTML =
        `<button class="btn btn--primary btn--full" onclick="closeModal()">${tr('closeBtn')}</button>`;
    document.getElementById('modal-overlay').classList.add('is-shown');
}

function closeModal() {
    document.getElementById('modal-overlay').classList.remove('is-shown');
}

document.addEventListener('click', e => {
    if (e.target.id === 'modal-overlay') closeModal();
});


// ═══════════════════════════════════════════════════════════════════════
// 15. ACCOUNTS
// ═══════════════════════════════════════════════════════════════════════

async function initAccounts() {
    if (typeof FB === 'undefined') { console.warn('[App] FB not ready for initAccounts, retrying...'); setTimeout(initAccounts, 500); return; }
    const session = readSessionState();
    if (session.name || session.id || session.key) {
        state.currentUser = session.name || null;
        state.userId = session.id || null;
        state.userKey = session.key || session.id || null;
        state.userAvatar = session.avatar || '👤';
        try {
            let user = null;
            const lookupId = state.userKey || state.userId;
            if (lookupId) {
                user = await FB.getUserById(lookupId);
            }
            if (!user && state.currentUser) {
                user = await FB.getUserByName(state.currentUser);
            }
            if (user) {
                state.currentUser = user.displayName || state.currentUser;
                state.userId = user.id ?? state.userId;
                state.userKey = user._key || user.public_id || user.userId || state.userKey;
                state.spentPoints = user.spent_points || user.spentPoints || 0;
                state.earnedPoints = user.earned_points || user.earnedPoints || 0;
                state.claimedCoupons = user.claimed_coupons || [];
                state.userAvatar = user.photoUrl || session.avatar || '👤';
                persistSessionState({
                    name: state.currentUser,
                    id: state.userId,
                    key: state.userKey,
                    avatar: state.userAvatar,
                });
            } else {
                state.userAvatar = session.avatar || '👤';
            }
        } catch (_) {
            state.userAvatar = session.avatar || '👤';
        }
    }
    updateHeaderUI();
}

function updateHeaderUI() {
    const avatarEl = document.getElementById('hdr-avatar');
    if (state.userAvatar && state.userAvatar.startsWith('data:') && state.userAvatar.length > 100) {
        avatarEl.innerHTML = `<img src="${state.userAvatar}" decoding="async" style="width:100%;height:100%;border-radius:50%;object-fit:cover" onerror="this.parentElement.textContent='👤'">`;
        avatarEl.style.background = 'none';
    } else {
        avatarEl.textContent = state.userAvatar || '👤';
        avatarEl.style.background = '';
    }
    document.getElementById('hdr-user').textContent = state.currentUser || tr('notLoggedIn');
    document.getElementById('hdr-user').style.display = state.currentUser ? 'block' : 'none';
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) logoutBtn.style.display = state.currentUser ? '' : 'none';
}

function handleAvatarClick() {
    if (!state.currentUser) {
        showUserPicker();
        return;
    }
    const avatars = ['🌿','♻️','🌱','🍃','🌳','💚','🌍','🪴','🐼','🐨','🦊','🐸','🌺','🍀','🌊','🔥','⭐','🌈','🦋','🐝'];
    const list = avatars.map(a => `
        <button class="btn btn--outline" style="font-size:28px;padding:8px;min-width:48px"
                onclick="setAvatar('${a}')">${a}</button>
    `).join('');
    document.getElementById('modal-icon').textContent = state.userAvatar;
    document.getElementById('modal-title').textContent = 'Choose Avatar';
    document.getElementById('modal-body').innerHTML = `
        <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-bottom:12px">${list}</div>
        <div style="text-align:center">
            <span class="text-muted text-sm">or</span>
            <button class="btn btn--outline btn--small mt-2" onclick="uploadAvatar()">📷 Upload Photo / GIF</button>
            <input type="file" id="avatar-file-input" accept="image/*" onchange="handleAvatarUpload(event)" class="hidden">
        </div>`;
    document.getElementById('modal-actions').innerHTML =
        `<button class="btn btn--outline btn--full" onclick="closeModal()">${tr('closeBtn')}</button>`;
    document.getElementById('modal-overlay').classList.add('is-shown');
    const modal = document.querySelector('#modal-overlay .modal');
    if (modal && MOTION_ENABLED) gsap.fromTo(modal, { scale: 0.85, opacity: 0, y: 16 }, { scale: 1, opacity: 1, y: 0, duration: 0.35, ease: "back.out(1.4)" });
}

function uploadAvatar() {
    document.getElementById('avatar-file-input').click();
}

function handleAvatarUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = '';
    const reader = new FileReader();
    reader.onload = () => {
        setAvatar(reader.result); // data URL
    };
    reader.readAsDataURL(file);
}

function setAvatar(emoji) {
    state.userAvatar = emoji;
    persistSessionState({
        name: state.currentUser,
        id: state.userId,
        key: state.userKey,
        avatar: emoji,
    });
    updateHeaderUI();
    // Save to backend storage
    if (state.userKey || state.userId) {
        FB.saveUserData(state.userKey || state.userId, { photoUrl: emoji });
    }
    closeModal();
}

function resetSessionState() {
    state.currentUser = null;
    state.userAvatar = '👤';
    state.userId = null;
    state.userKey = null;
    state.spentPoints = 0;
    state.earnedPoints = 0;
    state.claimedCoupons = [];
    invalidateRecordsCache({ clear: true });
    state.lastScanResult = null;
    if (typeof resetNearbyRecyclingUI === 'function') {
        resetNearbyRecyclingUI();
    }
    clearSessionState();
    updateHeaderUI();
}

function handleLogout() {
    if (!state.currentUser) return;
    showConfirm(tr('confirmLogout'), () => {
        resetSessionState();
        window.location.replace('/login');
    });
}

function toggleLogin() {
    if (state.currentUser) {
        showConfirm(tr('confirmLogout'), () => {
            resetSessionState();
            window.location.replace('/login');
        });
        return;
    }
    showUserPicker();
}

async function showUserPicker() {
    try {
        const users = await FB.getAllUsers();
        document.getElementById('modal-icon').textContent = '👤';
        document.getElementById('modal-title').textContent = tr('loginAs');
        const list = users.map(u => `
            <button class="btn btn--outline btn--full" style="margin-bottom:6px;justify-content:flex-start;gap:8px"
                    onclick='loginAs(${JSON.stringify(u.displayName || '')}, ${JSON.stringify(u.photoUrl || '👤')}, ${JSON.stringify(String(u.id ?? ''))}, ${JSON.stringify(u.public_id || u.userId || '')})'>
                <span style="font-size:20px">${u.photoUrl || '👤'}</span>
                <span>${esc(u.displayName || '')}</span>
            </button>
        `).join('');
        document.getElementById('modal-body').innerHTML = list;
        document.getElementById('modal-actions').innerHTML =
            `<button class="btn btn--outline btn--full" onclick="closeModal()">${tr('cancelBtn')}</button>`;
        document.getElementById('modal-overlay').classList.add('is-shown');
    } catch (_) { /* offline */ }
}

async function loginAs(name, avatar, userId, userKey = null) {
    state.currentUser = name;
    state.userAvatar = avatar;
    state.userId = userId || null;
    state.userKey = userKey || null;
    invalidateRecordsCache({ clear: true });
    persistSessionState({
        name,
        id: state.userId,
        key: state.userKey,
        avatar,
    });
    try {
        const lookupId = state.userId || state.userKey || name;
        const user = await FB.getUserById(lookupId);
        if (user) {
            state.currentUser = user.displayName || name;
            state.userId = user.id ?? state.userId;
            state.userKey = user._key || user.public_id || user.userId || state.userKey;
            state.spentPoints = user.spent_points || 0;
            state.earnedPoints = user.earned_points || 0;
            state.claimedCoupons = user.claimed_coupons || [];
            state.userAvatar = user.photoUrl || avatar || '👤';
            persistSessionState({
                name: state.currentUser,
                id: state.userId,
                key: state.userKey,
                avatar: state.userAvatar,
            });
        }
    } catch (_) { /* offline */ }
    closeModal();
    updateHeaderUI();
    navigateTo('home');
}

async function saveUserData() {
    if (!state.currentUser) return;
    const id = state.userKey || state.userId;
    if (!id) return;
    const data = {
        spent_points: state.spentPoints,
        earned_points: state.earnedPoints,
        claimed_coupons: state.claimedCoupons,
    };
    // Retry up to 3 times with backoff
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            await FB.saveUserData(id, data);
            return;
        } catch (e) {
            if (attempt < 2) await new Promise(r => setTimeout(r, 300 * (attempt + 1)));
        }
    }
}

window.addEventListener('beforeunload', () => {
    if (state.currentUser) saveUserData();
});


// ═══════════════════════════════════════════════════════════════════════
// 14b. LOGIN PAGE
// ═══════════════════════════════════════════════════════════════════════

let loginLang = safeStorage.get('RE_LIFE_LANG') || 'en';

function initLoginPage() {
    loginLang = safeStorage.get('RE_LIFE_LANG') || 'en';
    state.lang = loginLang; // sync with main state
    applyLoginLabels();
}

function applyLoginLabels() {
    const map = {
        'login-tagline': 'loginTagline',
        'lbl-username': 'usernameLabel',
        'lbl-password': 'passwordLabel',
        'lbl-login-btn': 'loginBtn',
        'lbl-register-btn': 'registerBtn',
        'lbl-or': 'orDivider',
        'lbl-version': 'versionLabel',
        'lbl-reg-username': 'regUsernameLabel',
        'lbl-reg-password': 'regPasswordLabel',
        'lbl-create-account-btn': 'createAccountBtn',
        'lbl-back-login': 'backToLogin',
    };
    for (const [id, key] of Object.entries(map)) {
        const el = document.getElementById(id);
        if (el) el.textContent = STRINGS[loginLang][key];
    }
    const langBtn = document.getElementById('lang-btn');
    if (langBtn) langBtn.textContent = loginLang === 'en' ? '🌐 EN' : '🌐 中文';
}

function toggleLoginLang() {
    loginLang = loginLang === 'en' ? 'zh' : 'en';
    safeStorage.set('RE_LIFE_LANG', loginLang);
    state.lang = loginLang;
    applyLoginLabels();
}

function toggleRegister() {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const showRegister = loginForm.classList.contains('hidden');
    if (showRegister) {
        loginForm.classList.add('hidden');
        registerForm.classList.remove('hidden');
    } else {
        registerForm.classList.add('hidden');
        loginForm.classList.remove('hidden');
    }
    document.getElementById('login-error').textContent = '';
    document.getElementById('register-error').textContent = '';
}

// ═══════════════════════════════════════════════════════════════════════
// 16. LANGUAGE
// ═══════════════════════════════════════════════════════════════════════

async function toggleLang() {
    state.lang = state.lang === 'en' ? 'zh' : 'en';
    safeStorage.set('RE_LIFE_LANG', state.lang);
    if (typeof I18N !== 'undefined') await I18N.load(state.lang);
    document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-HK';
    const langInd = document.getElementById('lang-ind');
    if (langInd) langInd.textContent = state.lang === 'en' ? 'Eng' : '中文';
    updateAllLabels();
    updateWeatherUI();
    if (state.activeTab === 'record') renderRecords();
    if (state.activeTab === 'rewards') renderRewards();
}

function updateAllLabels() {
    // Map of element IDs → translation keys
    const map = {
        'lbl-upload-text': 'uploadPhoto',
        'lbl-dispose-btn': 'toDispose',
        'lbl-purchase-btn': 'toPurchase',
        'lbl-dispose-sub': 'disposeSub',
        'lbl-purchase-sub': 'purchaseSub',
        'lbl-green-tips-pill': 'greenTips',
        'lbl-know-more': 'knowMore',
        'lbl-scan-title': 'scanItems',
        'lbl-upload-hint': 'orDrag',
        'lbl-scan-again': 'scanAgain',
        'lbl-add-record': 'addToRecord',
        'lbl-empty-text': 'noRecords',
        'lbl-empty-hint': 'noRecordsHint',
        'lbl-green-tips-pill': 'greenTips',
        'lbl-know-more': 'knowMore',
        'lbl-item-type': 'itemType',
        'lbl-item-state': 'itemState',
        'lbl-scanning-text': 'scanning',
        'lbl-scanning-hint': 'scanningHint',
        'ws-title': 'criteria',
        'lbl-overall': 'overallScore',
        'lbl-grade': 'grade',
        'lbl-advice': 'advice',
        'lbl-dg-title': 'disposalGuide',
        'lbl-disp-material': 'material',
        'lbl-disp-method': 'method',
        'lbl-disp-location': 'location',
        'lbl-disp-reuse': 'reuse',
        'lbl-nearby-recycling-title': 'recycling.nearbyTitle',
        'lbl-fact-title': 'didYouKnow',
        'lbl-weather-temperature': 'weather.detail.temperature',
        'lbl-weather-location': 'weather.detail.location',
        'lbl-weather-updated': 'weather.detail.updated',
        'lbl-weather-source': 'weather.detail.source',
        'lbl-weather-close': 'weather.detail.close',
        'lbl-rew-balance': 'pointsBalance',
        'lbl-rew-sub': 'rewardsSub',
        'lbl-my-coupons': 'myCoupons',
        'lbl-view-claimed': 'viewClaimed',
        'lbl-marketplace': 'ecoMarketplace',
        'lbl-claimed-title': 'claimedCoupons',
        'lbl-settings': 'settings',
        'lbl-theme': 'theme',
        'lbl-policy': 'policy',
        'logout-label': 'logout',
        'sound-label': 'soundOn',
        'theme-label': 'darkMode',
        'lang-label': 'language',
        'debug-label': 'debugOff',
        'nav-lbl-home': 'navHome',
        'nav-lbl-record': 'navRecord',
        'nav-lbl-rewards': 'navRewards',
        'nav-lbl-more': 'navMore',
    };

    Object.entries(map).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = tr(key);
    });

    // Dynamic labels
    const mp = document.getElementById('mode-purchase');
    const md = document.getElementById('mode-dispose');
    if (mp) mp.textContent = tr('purchaseMode');
    if (md) md.textContent = tr('disposalMode');

    // Schema dropdowns
    const typeSel = document.getElementById('schema-item-type');
    if (typeSel) {
        typeSel.options[0].text = tr('foodItems');
        typeSel.options[1].text = tr('generalItems');
    }
    const stateSel = document.getElementById('schema-item-state');
    if (stateSel) {
        stateSel.options[0].text = tr('newPurchase');
        stateSel.options[1].text = tr('aboutToExpire');
    }

    const sndIcon = document.getElementById('sound-icon');
    if (sndIcon) sndIcon.src = soundOn ? '/static/assets/Sound_On.png' : '/static/assets/Sound_Off.png';
    const sndLabel = document.getElementById('sound-label');
    if (sndLabel) sndLabel.textContent = soundOn ? tr('soundOn') : tr('soundOff');
    document.getElementById('clear-btn').textContent = tr('clearAll');
    updateHeaderUI();
}


// ═══════════════════════════════════════════════════════════════════════
// 17. SETTINGS
// ═══════════════════════════════════════════════════════════════════════

function toggleSound() {
    soundOn = !soundOn;
    const icon = document.getElementById('sound-icon');
    if (icon) icon.src = soundOn ? '/static/assets/Sound_On.png' : '/static/assets/Sound_Off.png';
    const label = document.getElementById('sound-label');
    if (label) label.textContent = soundOn ? tr('soundOn') : tr('soundOff');
}

// ── Theme Toggle ────────────────────────────────────────────────────

function initTheme() {
    const saved = safeStorage.get('RE_LIFE_THEME') || 'light';
    applyTheme(saved);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    safeStorage.set('RE_LIFE_THEME', theme);
    const sel = document.getElementById('theme-select');
    if (sel) sel.value = theme;
}

function refreshGradeColors() {
    // Refresh grade-tag pills and overall-score text color on all rendered elements
    document.querySelectorAll('.grade-tag').forEach(el => {
        const text = (el.textContent || '').trim();
        let score;
        if (text.includes('Excellent') || text.includes('(A)')) score = 90;
        else if (text.includes('Good') || text.includes('(B)')) score = 75;
        else if (text.includes('Fair') || text.includes('(C)')) score = 60;
        else if (text.includes('Poor') || text.includes('(D)')) score = 45;
        else score = 10;
        const g = getGrade(score);
        el.style.background = g.color;
    });

    // Refresh overall bar fill
    const bar = document.getElementById('ov-bar-fill');
    if (bar && state.lastScanResult) {
        const ov = state.lastScanResult.overall_score || 74;
        const g = getGrade(ov);
        bar.style.background = g.color;
    }

    // Refresh record card overall score text colors
    document.querySelectorAll('.record-card-ratings .rating-item:last-child span:last-child').forEach(el => {
        const val = parseInt(el.textContent) || 50;
        const g = getGrade(val);
        el.style.color = g.color;
    });

    // Refresh criterion bar fills
    document.querySelectorAll('.criterion-bar-fill').forEach(el => {
        const key = el.getAttribute('data-key');
        if (!key || !state.lastScanResult) return;
        const scores = state.lastScanResult.weighted_scores;
        if (!scores) return;
        const v = scores[key] || 50;
        el.style.background = getBarColor(v);
    });
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
    refreshGradeColors();
    renderRecords();
}

function openPolicy() {
    showAlert(tr('policy'), tr('policyText'));
}

function toggleDebug() {
    state.debugMode = !state.debugMode;
    const label = document.getElementById('debug-label');
    if (label) label.textContent = state.debugMode ? tr('debugOn') : tr('debugOff');
}

// ── Click Ripple Initialization ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const addRippleEffect = (e) => {
        const btn = e.target.closest('.btn--primary, .scan-btn, .login-btn--primary');
        if (!btn) return;

        // Create ripple element
        const ripple = document.createElement('span');
        ripple.className = 'click-ripple';
        
        // Calculate click coordinates
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        ripple.style.left = `${x}px`;
        ripple.style.top = `${y}px`;
        
        // Append and auto-cleanup
        btn.appendChild(ripple);
        setTimeout(() => ripple.remove(), 600);
    };

    document.body.addEventListener('click', addRippleEffect);
});
