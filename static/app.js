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
// 3. APP STATE
// ═══════════════════════════════════════════════════════════════════════

const state = {
    activeTab: 'home',
    scanMode: 'dispose',
    selectedFile: null,
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
};


// ═══════════════════════════════════════════════════════════════════════
// 5. INITIALIZATION  (sound/beep in utils.js)
// ═══════════════════════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════
// HEADER DRAG + NAV SWIPE
// ═══════════════════════════════════════════════════════════════════════

function setupFluidDraggable(element) {
    if (!element) return;

    let isDragging = false;
    let startX, startY;
    let translateX = 0;
    let translateY = 0;

    element.addEventListener('pointerdown', (e) => {
        if (e.target.closest('button') || e.target.closest('input') || e.target.closest('select') || e.target.id === 'hdr-avatar') {
            return;
        }

        isDragging = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;

        element.setPointerCapture(e.pointerId);
        element.style.transition = 'none';
    });

    element.addEventListener('pointermove', (e) => {
        if (!isDragging) return;

        let nextX = e.clientX - startX;
        let nextY = e.clientY - startY;

        const rect = element.getBoundingClientRect();
        const appContainer = element.closest('.app') || document.body;
        const containerRect = appContainer.getBoundingClientRect();

        const originalLeft = element.offsetLeft;
        const originalTop = element.offsetTop;

        const minX = -originalLeft;
        const maxX = containerRect.width - originalLeft - rect.width;
        const minY = -originalTop;
        const maxY = containerRect.height - originalTop - rect.height;

        translateX = Math.max(minX, Math.min(nextX, maxX));
        translateY = Math.max(minY, Math.min(nextY, maxY));

        element.style.transform = `translate3d(${translateX}px, ${translateY}px, 0)`;
    });

    const stopDrag = (e) => {
        if (!isDragging) return;
        isDragging = false;
        element.releasePointerCapture(e.pointerId);
    };

    element.addEventListener('pointerup', stopDrag);
    element.addEventListener('pointercancel', stopDrag);
}

const TAB_ORDER = ['home', 'record', 'rewards', 'more'];

function setupNavSwipe() {
    const nav = document.querySelector('nav.nav');
    if (!nav) return;

    let startX = 0;
    let startY = 0;

    nav.addEventListener('touchstart', (e) => {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
    }, { passive: true });

    nav.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - startX;
        const dy = e.changedTouches[0].clientY - startY;

        if (Math.abs(dx) < 30 || Math.abs(dx) < Math.abs(dy)) return;

        const currentIdx = TAB_ORDER.indexOf(state.activeTab);
        if (dx < 0 && currentIdx < TAB_ORDER.length - 1) {
            navigateTo(TAB_ORDER[currentIdx + 1]);
        } else if (dx > 0 && currentIdx > 0) {
            navigateTo(TAB_ORDER[currentIdx - 1]);
        }
    });
}

function initDraggableBars() {
    setupNavSwipe();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDraggableBars);
} else {
    initDraggableBars();
}

document.addEventListener('DOMContentLoaded', async () => {
    // Detect login page vs main app
    if (document.querySelector('.login-page')) {
        initLoginPage();
        return;
    }

    // Main app — redirect to login if no session
    if (!safeStorage.get('RE_LIFE_CURRENT_USER')) {
        window.location.replace('/login');
        return;
    }

    // Init language from storage
    state.lang = safeStorage.get('RE_LIFE_LANG') || 'en';
    // Fire i18n load but don't block render
    if (typeof I18N !== 'undefined') I18N.load(state.lang).then(updateAllLabels);
    document.documentElement.lang = state.lang === 'zh' ? 'zh-HK' : 'en';
    updateAllLabels();

    startClock();
    setupDragDrop();
    initNavDrag();
    initTheme();
    setScanModeUI('dispose');
    updateHeaderUI();

    // Critical: load user + records first
    const [_, __] = await Promise.all([initAccounts(), loadRecords()]);

    // Non-critical: lazy load in background
    requestIdleCallback ? requestIdleCallback(() => {
        loadTips(); loadRewards(); loadFact(); detectCamera();
    }) : setTimeout(() => {
        loadTips(); loadRewards(); loadFact(); detectCamera();
    }, 500);
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
// 5.5 NAV BAR DRAG/SWIPE
// ═══════════════════════════════════════════════════════════════════════

function initNavDrag() {
    const navbar = document.querySelector('nav.nav, .app-nav');
    if (!navbar) return;
    const indicator = document.getElementById('nav-indicator');
    const btns = navbar.querySelectorAll('.nav-btn');
    let isDragging = false;

    // Position indicator under active tab initially
    function snapIndicatorTo(btn) {
        if (!indicator || !btn) return;
        const nr = navbar.getBoundingClientRect();
        const br = btn.getBoundingClientRect();
        const targetX = br.left - nr.left;
        const curX = parseFloat(indicator.style.left) || 0;
        const dx = targetX - curX;

        gsap.to(indicator, {
            left: targetX,
            width: br.width,
            scaleX: 1,
            duration: isDragging ? 0.15 : 0.4,
            ease: isDragging ? "power2.out" : "elastic.out(1, 0.5)",
            overwrite: "auto",
        });
        // Jelly squash in direction of movement
        if (!isDragging && Math.abs(dx) > 10) {
            const dir = dx > 0 ? 1 : -1;
            gsap.fromTo(indicator, 
                { scaleX: 1 + dir * 0.08 },
                { scaleX: 1, duration: 0.5, ease: "elastic.out(1, 0.4)", overwrite: "auto" }
            );
        }
    }

    // Initial snap
    const activeBtn = navbar.querySelector('.nav-btn.is-active');
    if (activeBtn) snapIndicatorTo(activeBtn);

    function evalTab(clientX) {
        const nr = navbar.getBoundingClientRect();
        const relX = clientX - nr.left;

        // Find which two buttons the finger is between for smooth interpolation
        let leftBtn = null, rightBtn = null;
        const btnArray = Array.from(btns);
        for (let i = 0; i < btnArray.length; i++) {
            const r = btnArray[i].getBoundingClientRect();
            const btnCenter = r.left - nr.left + r.width / 2;
            if (btnCenter <= relX) leftBtn = { el: btnArray[i], rect: r, center: btnCenter };
            if (btnCenter >= relX && !rightBtn) rightBtn = { el: btnArray[i], rect: r, center: btnCenter };
        }

        // Smoothly interpolate indicator position between adjacent buttons
        if (indicator) {
            if (leftBtn && rightBtn && leftBtn.el !== rightBtn.el) {
                const range = rightBtn.center - leftBtn.center;
                const t = range > 0 ? (relX - leftBtn.center) / range : 0;
                const l = leftBtn.rect.left - nr.left + t * (rightBtn.rect.left - leftBtn.rect.left);
                const w = leftBtn.rect.width + t * (rightBtn.rect.width - leftBtn.rect.width);
                // Jelly during drag: slight width overshoot in movement direction
                const dragScale = 0.97 + 0.06 * Math.abs(t - 0.5) * 2; // narrower at midpoint, wider near edges
                gsap.to(indicator, { left: l, width: w, scaleX: dragScale, duration: 0.1, ease: "power1.out", overwrite: "auto" });
            } else if (rightBtn) {
                const r = rightBtn.rect;
                gsap.to(indicator, { left: r.left - nr.left, width: r.width, scaleX: 1, duration: 0.12, ease: "power2.out", overwrite: "auto" });
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
            const m = (best.getAttribute('onclick') || '').match(/navigateTo\(['"]([^'"]+)['"]\)/);
            if (m && m[1] && state.activeTab !== m[1]) navigateTo(m[1]);
        }
    }

    // Dynamic refraction — stronger during drag
    const svgFilter = document.getElementById('liquid-distortion');
    const displacementMap = svgFilter?.querySelector('feDisplacementMap');
    let currentScale = 4;

    function setRefraction(scale) {
        if (!displacementMap) return;
        currentScale += (scale - currentScale) * 0.15;
        displacementMap.setAttribute('scale', String(Math.round(currentScale)));
    }

    navbar.addEventListener('pointerdown', e => {
        if (e.button !== 0) return;
        isDragging = true;
        navbar.classList.add('nav-is-dragging');
        navbar.setPointerCapture(e.pointerId);
        evalTab(e.clientX);
        // Animate refraction up
        const step = () => { if (isDragging) { setRefraction(12); requestAnimationFrame(step); } else { setRefraction(4); } };
        requestAnimationFrame(step);
    });
    navbar.addEventListener('pointermove', e => { if (isDragging) evalTab(e.clientX); });
    const stop = e => {
        isDragging = false;
        navbar.classList.remove('nav-is-dragging');
        try { navbar.releasePointerCapture(e.pointerId); } catch {}
        const active = navbar.querySelector('.nav-btn.is-active');
        if (active) snapIndicatorTo(active);
    };
    navbar.addEventListener('pointerup', stop);
    navbar.addEventListener('pointercancel', stop);

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

function navigateTo(name) {
    // Kill any in-progress tab animation
    if (_tabTween) { _tabTween.kill(); _tabTween = null; }

    state.activeTab = name;
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('is-active'));
    const nav = document.getElementById(`nav-${name}`);
    if (nav) { nav.classList.add('is-active'); if (window._snapNavIndicator) window._snapNavIndicator(); }

    const currentTab = document.querySelector('.tab.active');
    const nextTab = document.getElementById(`tab-${name}`);
    if (!nextTab) return;
    if (currentTab === nextTab) return;

    // Immediately clean up all tabs
    document.querySelectorAll('.tab').forEach(t => { t.classList.remove('active'); gsap.set(t, { clearProps: "all" }); });
    nextTab.classList.add('active');

    // Animate new tab in
    gsap.fromTo(nextTab, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.3, ease: "power2.out" });

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
        gsap.fromTo(active, { scale: 0.92 }, { scale: 1.04, duration: 0.35, ease: "elastic.out(1, 0.4)" });
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
            gsap.to(zone, { scale: 1.02, duration: 0.2, ease: "power2.out" });
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
        showPreview(reader.result);
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
    gsap.from(preview, { scale: 0.9, opacity: 0, duration: 0.35, ease: "back.out(1.4)" });
}

function clearPreview() {
    state.selectedFile = null;
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
// 8b. CAMERA CAPTURE
// ═══════════════════════════════════════════════════════════════════════

let cameraStream = null;
let cameraFacing = 'environment'; // 'environment' (rear) or 'user' (front)

function zoneTap() {
    if (state.selectedFile) return; // preview is showing, ignore tap
    if (cameraAvailable) {
        openCamera();
    } else {
        triggerUpload();
    }
}

async function openCamera() {
    const modal = document.getElementById('camera-modal');
    const video = document.getElementById('camera-video');
    if (!modal || !video) { cameraAvailable = false; triggerUpload(); return; }

    // Show modal first so the video element is in the visible DOM
    // (required by iOS Safari before attaching a stream)
    modal.classList.add('is-shown');
    document.body.style.overflow = 'hidden';
    gsap.fromTo(modal, { y: '100%' }, { y: 0, duration: 0.3, ease: "power2.out" });
    document.body.classList.add('camera-active');

    // iOS-friendly constraints: avoid width/height which some iOS versions reject
    const constraints = [
        { video: { facingMode: cameraFacing }, audio: false },
        { video: { facingMode: { ideal: cameraFacing } }, audio: false },
        { video: true, audio: false },
    ];

    for (const c of constraints) {
        try {
            cameraStream = await navigator.mediaDevices.getUserMedia(c);
            video.srcObject = cameraStream;
            video.play().catch(() => {});
            return; // success
        } catch (_) {
            // try next constraint set
        }
    }

    // All attempts failed — camera unavailable, fall back to file picker permanently
    cameraAvailable = false;
    closeCamera();
    triggerUpload();
}

function closeCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
    document.getElementById('camera-modal').classList.remove('is-shown');
    document.getElementById('camera-video').srcObject = null;
    document.body.style.overflow = '';
    // Restore floating nav and header
    document.body.classList.remove('camera-active');
}

function flipCamera() {
    cameraFacing = cameraFacing === 'environment' ? 'user' : 'environment';
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
    const video = document.getElementById('camera-video');
    if (!video) return;

    const constraints = [
        { video: { facingMode: cameraFacing }, audio: false },
        { video: { facingMode: { ideal: cameraFacing } }, audio: false },
        { video: true, audio: false },
    ];

    (async () => {
        for (const c of constraints) {
            try {
                cameraStream = await navigator.mediaDevices.getUserMedia(c);
                video.srcObject = cameraStream;
                video.play().catch(() => {});
                return;
            } catch (_) {}
        }
    })();
}

function capturePhoto() {
    const video = document.getElementById('camera-video');
    const canvas = document.getElementById('camera-canvas');

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(blob => {
        if (!blob) { closeCamera(); return; }
        const file = new File([blob], 'camera-photo.jpg', { type: 'image/jpeg' });
        closeCamera();
        processFile(file);
    }, 'image/jpeg', 0.92);
    playBeep('beep');
}


// ═══════════════════════════════════════════════════════════════════════
// 9. SCAN (Mock + Gemini AI)
// ═══════════════════════════════════════════════════════════════════════

async function doScan() {
    if (!state.selectedFile) return;

    const status = document.getElementById('scan-status');
    status.classList.add('is-shown');
    gsap.fromTo(status, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.3 });
    document.getElementById('scan-result').classList.add('hidden');

    try {
        const fd = new FormData();
        fd.append('file', state.selectedFile);
        fd.append('mode', state.scanMode);
        fd.append('item_type', state.itemType);
        fd.append('item_state', state.itemState);
        if (state.debugMode) fd.append('debug', 'true');

        const res = await fetch('/api/scan/ai', { method: 'POST', body: fd });
        const data = await res.json();

        // If AI failed, fall back to on-device CNN classifier
        if (data.classifier_fallback) {
            throw new Error('classifier_fallback');
        }

        data.mode = data.mode || state.scanMode;

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
        const msg = (err.message || String(err));
        document.getElementById('scan-result').classList.remove('hidden');
        document.getElementById('result-name').textContent = 'Scan Error';
        document.getElementById('result-desc').textContent = msg;
        document.getElementById('result-brand').textContent = '';
        document.getElementById('gemini-error').textContent = '❌ ' + msg;
        document.getElementById('gemini-error').style.display = 'block';
        playBeep('error');
    } finally {
        document.getElementById('scan-status').classList.remove('is-shown');
    }
}

// ── Bar drag handlers ──────────────────────────────────────────────
let barDragState = null;

function startBarDrag(e) {
    e.preventDefault();
    const bar = e.currentTarget;
    const fill = bar.querySelector('.criterion-bar-fill');
    const key = bar.dataset.key;
    const rect = bar.getBoundingClientRect();
    barDragState = { bar, fill, key, rect };
    updateBarFromEvent(e);
    window.addEventListener('mousemove', onBarDrag);
    window.addEventListener('mouseup', stopBarDrag);
    window.addEventListener('touchmove', onBarDrag, { passive: false });
    window.addEventListener('touchend', stopBarDrag);
}

function onBarDrag(e) {
    e.preventDefault();
    updateBarFromEvent(e);
}

function updateBarFromEvent(e) {
    if (!barDragState) return;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const { bar, fill, key, rect } = barDragState;
    let pct = Math.round(((clientX - rect.left) / rect.width) * 100);
    pct = Math.max(0, Math.min(100, pct));
    fill.style.width = pct + '%';
    const barColor = pct >= 70 ? '#065f46' : pct >= 50 ? '#ca8a04' : '#dc2626';
    fill.style.background = barColor;
    const scoreEl = bar.parentElement.querySelector('.criterion-score');
    if (scoreEl) scoreEl.textContent = pct + '/100';
    // Update state
    if (state.lastScanResult && state.lastScanResult.weighted_scores) {
        state.lastScanResult.weighted_scores[key] = pct;
    }
    // Recalc overall
    recalcOverall();
}

function stopBarDrag() {
    barDragState = null;
    window.removeEventListener('mousemove', onBarDrag);
    window.removeEventListener('mouseup', stopBarDrag);
    window.removeEventListener('touchmove', onBarDrag);
    window.removeEventListener('touchend', stopBarDrag);
}

function recalcOverall() {
    if (!state.lastScanResult) return;
    const scores = state.lastScanResult.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 };
    const schemaId = state.lastScanResult.schema_id || 'food_new';
    const ov = calcWeighted(scores, schemaId);
    const g = getGrade(ov);
    state.lastScanResult.overall_score = ov;
    state.lastScanResult.grade = g.grade;
    state.lastScanResult.grade_advice = g.advice;
    state.lastScanResult.grade_color = g.color;
    document.getElementById('ov-score').textContent = ov;
    document.getElementById('ov-bar-fill').style.cssText = `width:${ov}%;background:${g.color}`;
    document.getElementById('grade-tag').textContent = g.grade;
    document.getElementById('grade-tag').style.background = g.color;
    document.getElementById('grade-advice').textContent = g.advice;
}

function showScanResult(item) {
    const result = document.getElementById('scan-result');
    result.classList.remove('hidden');
    // GSAP entrance animation
    gsap.fromTo(result, { opacity: 0, y: 20, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.4, ease: "power2.out" });

    // Image
    const imgContainer = document.getElementById('result-img');
    imgContainer.textContent = item.mode === 'purchase' ? '🥛' : '🗑️';
    if (item.image_url) {
        const img = document.createElement('img');
        img.src = item.image_url;
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:12px';
        imgContainer.textContent = '';
        imgContainer.appendChild(img);
    }

    // Basic info
    document.getElementById('result-name').textContent = item.name;
    document.getElementById('result-desc').textContent = item.description || '';
    document.getElementById('result-brand').textContent = item.brand || item.category || '';

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

    // Star ratings
    renderStars('result-eco-stars', item.eco_rate);
    renderStars('result-recycle-stars', item.recycle_rate);

    // Alternative product (purchase mode only)
    const isPurchase = item.mode === 'purchase';
    const alt = document.getElementById('result-alt');
    if (item.alternative && isPurchase) {
        alt.classList.remove('hidden');
        document.getElementById('alt-name').textContent = item.alternative.name;
        renderStars('alt-eco-stars', item.alternative.eco_rate);
        renderStars('alt-recycle-stars', item.alternative.recycle_rate);
        gsap.from(alt, { opacity: 0, y: 12, duration: 0.35, ease: "power2.out" });
    } else {
        alt.classList.add('hidden');
    }

    // Prove button — only in purchase mode
    const proveBtn = document.getElementById('lbl-prove-swap');
    if (proveBtn) {
        if (isPurchase && item.alternative) {
            proveBtn.classList.remove('hidden');
            proveBtn.textContent = '📸 Prove You Swapped → Earn +50 Pts';
            proveBtn.style.background = '';
            proveBtn.disabled = false;
        } else {
            proveBtn.classList.add('hidden');
        }
    }

    // Weighted score breakdown
    const schemaId = item.schema_id || 'food_new';
    const overall = item.overall_score ||
        calcWeighted(item.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 }, schemaId);
    const grade = item.grade ? { grade: item.grade, color: item.grade_color } : getGrade(overall);

    document.getElementById('ov-score').textContent = overall;
    const barFill = document.getElementById('ov-bar-fill');
    if (barFill) {
        barFill.style.transformOrigin = 'left center';
        gsap.fromTo(barFill, { scaleX: 0 }, { scaleX: overall / 100, duration: 0.8, ease: "power3.out" });
        barFill.style.backgroundColor = grade.color;
        barFill.style.width = `${overall}%`; // set actual width for layout
    }
    document.getElementById('grade-tag').textContent = grade.grade;
    document.getElementById('grade-tag').style.background = grade.color;
    document.getElementById('grade-advice').textContent = item.grade_advice || '';

    // Criteria detail bars
    const labels = item.criteria_labels || CRITERIA_LABELS[schemaId] || CRITERIA_LABELS.food_new;
    const scores = item.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 };
    const weights = SCHEMA_WEIGHTS[schemaId] || SCHEMA_WEIGHTS.food_new;
    const detail = document.getElementById('weighted-detail');
    detail.innerHTML = '';

    for (const k of ['a', 'b', 'c', 'd', 'e']) {
        const v = scores[k] || 50;
        const w = Math.round(weights[k] * 100);
        const barColor = getBarColor(v);
        detail.innerHTML += `
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

    // Disposal guide
    const guide = document.getElementById('disposal-guide');
    const dispInfo = item.disposal_info;
    if (dispInfo || item.disposal_guide) {
        guide.classList.remove('hidden');
        if (dispInfo) {
            document.getElementById('disp-material').textContent = dispInfo.type || '';
            document.getElementById('disp-method').textContent = dispInfo.method || '';
            document.getElementById('disp-location').textContent = dispInfo.location || '';
        }
        document.getElementById('disp-guide').textContent = item.disposal_guide || '';
        document.getElementById('disp-prec').textContent = item.precaution || '';
    } else {
        guide.classList.add('hidden');
    }

    state.lastScanResult = item;
}

function toggleWS() {
    const detail = document.getElementById('weighted-detail');
    const btn = document.getElementById('ws-toggle-btn');
    const isOpen = detail.classList.toggle('is-open');
    btn.textContent = isOpen ? tr('hideDetails') : tr('showDetails');
    if (isOpen) {
        // Attach drag handlers after display becomes flex
        requestAnimationFrame(() => {
            detail.querySelectorAll('.criterion-bar').forEach(bar => {
                const fill = bar.querySelector('.criterion-bar-fill');
                if (fill) fill.classList.remove('is-animated');
                bar.addEventListener('mousedown', startBarDrag);
                bar.addEventListener('touchstart', startBarDrag, { passive: false });
            });
        });
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

    // Disable add button
    const addBtn = document.getElementById('lbl-add-record');
    if (addBtn) {
        addBtn.textContent = '✓ Added to Record';
        addBtn.disabled = true;
        addBtn.style.opacity = '0.6';
    }
    playBeep('success');

    // Save to Firebase
    FB.addItem(record).catch(err => console.error('Failed to save item:', err));
}

function swapAlternative() {
    if (!state.lastScanResult || !state.lastScanResult.alternative) return;
    const alt = state.lastScanResult.alternative;
    state.lastScanResult.name = alt.name;
    state.lastScanResult.eco_rate = alt.eco_rate;
    state.lastScanResult.recycle_rate = alt.recycle_rate;
    state.lastScanResult.alternative = null;
    state.lastScanResult.description = 'Swapped to eco-friendly alternative.';
    showScanResult(state.lastScanResult);
    playBeep('beep');
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
        setTimeout(() => { if (btn) btn.textContent = '📸 Prove You Swapped → Earn +50 Pts'; }, 2000);
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
        gsap.fromTo(btn, { scale: 1 }, { scale: 1.1, duration: 0.15, yoyo: true, repeat: 1, ease: "power2.out" });
    }
    // Refresh points display
    if (state.activeTab === 'rewards') renderRewards();
    playBeep('success');
}

function resetScan() {
    const result = document.getElementById('scan-result');
    if (!result.classList.contains('hidden')) {
        gsap.to(result, { opacity: 0, scale: 0.95, y: -10, duration: 0.25, ease: "power2.in", onComplete: () => {
            result.classList.add('hidden');
            result.style.opacity = ''; result.style.transform = '';
        }});
    } else {
        result.classList.add('hidden');
    }
    clearPreview();
    document.getElementById('weighted-detail').classList.remove('is-open');
    state.lastScanResult = null;
}


// ═══════════════════════════════════════════════════════════════════════
// 10. RECORDS
// ═══════════════════════════════════════════════════════════════════════

async function loadRecords() {
    try {
        const items = await FB.getItems(state.userId, state.currentUser, state.userKey);
        state.records = items.map(it => ({
            id: it.id,
            name: it.name,
            mode: it.status,
            eco_rate: it.eco_rate,
            recycle_rate: it.recycle_rate,
            overall_score: it.overall_score,
            material: it.material,
            grade: it.grade,
            description: it.description,
            image_url: it.photoUrl,
            disposal_guide: it.dealtWithMethod,
            disposal_info: null,
            precaution: null,
            alternative: it.alternative,
            weighted_scores: it.weighted_scores,
            schema_id: it.schema_id,
            brand: it.brand,
            category: it.category,
            image: it.status === 'purchase' ? '🥛' : '🗑️',
        }));
        renderRecords();
        updateStats();
    } catch (e) {
        console.error('Failed to load records:', e);
    }
}

function renderRecords() {
    const container = document.getElementById('records-list');
    const empty = document.getElementById('records-empty');

    if (!state.records.length) {
        container.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    container.innerHTML = state.records.map(r => {
        const schemaId = r.schema_id || 'food_new';
        const overall = r.overall_score ||
            calcWeighted(r.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 }, schemaId);
        const grade = getGrade(overall);

        // Alternative card
        let altHtml = '';
        if (r.alternative) {
            altHtml = `
                <div class="alternative-card">
                    <div class="alternative-card-label">${tr('alternativeProduct')}</div>
                    <div class="alternative-card-name">${esc(r.alternative.name)}</div>
                    <div class="alternative-card-ratings">
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoRate')}:</span>
                            <div class="star-rating">${buildStars(r.alternative.eco_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('recycleRate')}:</span>
                            <div class="star-rating">${buildStars(r.alternative.recycle_rate)}</div>
                        </div>
                    </div>
                </div>`;
        }

        // Disposal guide
        let guideHtml = '';
        if (r.disposal_guide || r.disposal_info) {
            guideHtml = `
                <div class="disposal-guide">
                    <div class="disposal-guide-title">♻️ ${tr('disposalGuide')}</div>
                    ${r.disposal_info ? `
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('material')}:</span> ${esc(r.disposal_info.type)}</div>
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('method')}:</span> ${esc(r.disposal_info.method)}</div>
                        <div class="disposal-guide-row"><span class="disposal-guide-label">${tr('location')}:</span> ${esc(r.disposal_info.location)}</div>
                    ` : ''}
                    ${r.disposal_guide ? `<div class="disposal-guide-row" style="margin-top:3px">${esc(r.disposal_guide)}</div>` : ''}
                    ${r.precaution ? `<div class="disposal-guide-precaution">⚠️ ${esc(r.precaution)}</div>` : ''}
                </div>`;
        }

        const photoHtml = r.image_url
            ? `<img src="${esc(r.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" alt="">`
            : (r.image || '📦');

        return `
        <div class="record-card" id="rec-${r.id}" onclick="viewRecordDetail('${r.id}')" style="cursor:pointer">
            <div class="record-card-inner">
                <div class="record-card-image">${photoHtml}</div>
                <div class="record-card-info">
                    <div class="record-card-name">${esc(r.name)}</div>
                    <div class="record-card-meta">
                        <span class="record-card-badge record-card-badge--${r.mode}">${r.mode === 'purchase' ? tr('purchaseBadge') : tr('disposeBadge')}</span>
                        <span class="grade-tag" style="background:${grade.color};font-size:8px">${grade.grade}</span>
                    </div>
                    <div class="record-card-ratings">
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoRate')}</span>
                            <div class="star-rating">${buildStars(r.eco_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('recycleRate')}</span>
                            <div class="star-rating">${buildStars(r.recycle_rate)}</div>
                        </div>
                        <div class="rating-item">
                            <span class="rating-label">${tr('ecoGradeLabel')}</span>
                            <span style="font-size:13px;font-weight:900;color:${grade.color}">${overall}/100</span>
                        </div>
                    </div>
                    ${altHtml}
                    ${guideHtml}
                </div>
            </div>
            <div class="record-card-actions">
                <button class="btn btn--outline btn--small" onclick="event.stopPropagation();viewRecordDetail('${r.id}')">🔍 Details</button>
                <button class="btn btn--danger" onclick="event.stopPropagation();deleteRecord('${r.id}')">🗑️</button>
            </div>
        </div>`;
    }).join('');

    // GSAP staggered card entrance
    gsap.fromTo('#records-list .record-card', 
        { opacity: 0, y: 24 }, 
        { opacity: 1, y: 0, duration: 0.4, stagger: 0.06, ease: "power2.out" }
    );
}

async function deleteRecord(id) {
    try {
        await FB.deleteItem(id);
        const card = document.getElementById(`rec-${id}`);
        if (card) {
            gsap.to(card, { opacity: 0, scaleY: 0, transformOrigin: 'top center', duration: 0.25, ease: "power2.in", onComplete: () => { card.style.display = 'none'; loadRecords(); } });
        }
    } catch (e) {
        console.error('Failed to delete record:', e);
    }
}

function viewRecordDetail(id) {
    const r = state.records.find(rec => rec.id === id);
    if (!r) return;

    const grade = getGrade(r.overall_score || 50);
    const photoHtml = r.image_url
        ? `<img src="${esc(r.image_url)}" style="width:100%;max-height:200px;object-fit:cover;border-radius:12px;margin-bottom:12px" alt="">`
        : `<div style="font-size:48px;text-align:center;margin-bottom:12px">${r.image || '📦'}</div>`;

    const guideHtml = (r.disposal_guide || r.material) ? `
        <div class="disposal-guide" style="margin-top:12px">
            <div class="disposal-guide-title">♻️ ${tr('disposalGuide')}</div>
            ${r.material ? `<div class="disposal-guide-row"><span class="disposal-guide-label">${tr('material')}:</span> ${esc(r.material)}</div>` : ''}
            ${r.disposal_guide ? `<div class="disposal-guide-row">${esc(r.disposal_guide)}</div>` : ''}
        </div>` : '';

    document.getElementById('modal-icon').textContent = '';
    document.getElementById('modal-title').textContent = r.name;
    document.getElementById('modal-body').innerHTML = `
        ${photoHtml}
        <div style="font-size:11px;color:var(--color-gray-500);margin-bottom:8px">${esc(r.description || '')}</div>
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px">
            <span class="record-card-badge record-card-badge--${r.mode}">${r.mode === 'purchase' ? tr('purchaseBadge') : tr('disposeBadge')}</span>
            <span class="grade-tag" style="background:${grade.color}">${grade.grade}</span>
        </div>
        <div style="display:flex;gap:16px;margin-bottom:10px">
            <div class="rating-item"><span class="rating-label">${tr('ecoRate')}</span><div class="star-rating">${buildStars(r.eco_rate)}</div></div>
            <div class="rating-item"><span class="rating-label">${tr('recycleRate')}</span><div class="star-rating">${buildStars(r.recycle_rate)}</div></div>
        </div>
        <div class="overall-row"><span class="overall-label">${tr('overallScore')}</span><div><span class="overall-value">${r.overall_score || 50}</span><span class="overall-max">/100</span></div></div>
        <div class="overall-bar" style="margin-bottom:0"><div class="overall-bar-fill" style="width:${r.overall_score || 50}%;background:${grade.color}"></div></div>
        ${guideHtml}
    `;
    document.getElementById('modal-actions').innerHTML = `
        <button class="btn btn--outline btn--full" onclick="closeModal()">${tr('closeBtn')}</button>
        <button class="btn btn--danger" onclick="closeModal();deleteRecord('${r.id}')">🗑️ ${tr('clearAll') || 'Delete'}</button>
    `;
    document.getElementById('modal-overlay').classList.add('is-shown');
}

async function clearAllRecords() {
    showConfirm(tr('confirmClear'), async () => {
        await FB.clearAllItems();
        state.records = [];
        renderRecords();
        updateStats();
    });
}

function updateStats() {
    const n = state.records.length;
    const itemsEl = document.getElementById('stat-items');
    const ecoEl = document.getElementById('stat-eco');
    const recycleEl = document.getElementById('stat-recycle');

    const animateEl = (el, value) => {
        el.textContent = value;
        el.classList.remove('anim-entrance');
        void el.offsetWidth; // force reflow
        el.classList.add('anim-entrance');
    };

    animateEl(itemsEl, n);
    animateEl(ecoEl, n
        ? (state.records.reduce((s, r) => s + (r.eco_rate || 3), 0) / n).toFixed(1)
        : '0');
    animateEl(recycleEl, n
        ? (state.records.reduce((s, r) => s + (r.recycle_rate || 3), 0) / n).toFixed(1)
        : '0');
}


// ═══════════════════════════════════════════════════════════════════════
// 11. TIPS & FACTS
// ═══════════════════════════════════════════════════════════════════════

async function loadTips() {
    try {
        const res = await fetch('/api/news');
        const news = await res.json();
        state.tips = news.map(n => ({
            title: n.title,
            source: n.source,
            snippet: '',
            link: n.link || '',
        }));
        renderTipsDots();
        showTip(0);
    } catch (e) {
        console.error('Failed to load news:', e);
    }
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
    const titleEl = document.getElementById('tips-title');
    const snippetEl = document.getElementById('tips-snippet');
    if (titleEl) titleEl.classList.add('is-switching');
    if (snippetEl) snippetEl.classList.add('is-switching');
    setTimeout(() => {
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
// 12. REWARDS
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

    // GSAP staggered entrance for rewards
    gsap.fromTo('#rew-catalogue .rewards-item', 
        { opacity: 0, y: 16 }, 
        { opacity: 1, y: 0, duration: 0.35, stagger: 0.05, ease: "power2.out" }
    );

    // Claimed coupons grid
    const grid = document.getElementById('rew-coupon-grid');
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
// 13. MODALS
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
    if (modal) gsap.fromTo(modal, { scale: 0.85, opacity: 0, y: 16 }, { scale: 1, opacity: 1, y: 0, duration: 0.35, ease: "back.out(1.4)" });
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
// 14. USER ACCOUNTS
// ═══════════════════════════════════════════════════════════════════════

async function initAccounts() {
    const stored = safeStorage.get('RE_LIFE_CURRENT_USER');
    if (stored) {
        state.currentUser = stored;
        state.userAvatar = safeStorage.get('RE_LIFE_USER_AVATAR') || user.photoUrl || '👤';
        try {
            const user = await FB.getUserByName(stored);
            if (user) {
                console.log("[App] initAccounts user:", { id: user.id, _key: user._key, earned_points: user.earned_points, spent_points: user.spent_points });
                state.userId = user.id;
                state.userKey = user._key || null;
                state.spentPoints = user.spent_points || user.spentPoints || 0;
                state.earnedPoints = user.earned_points || user.earnedPoints || 0;
                state.claimedCoupons = user.claimed_coupons || [];
            }
        } catch (_) { /* offline */ }
    }
    updateHeaderUI();
}

function updateHeaderUI() {
    const avatarEl = document.getElementById('hdr-avatar');
    if (state.userAvatar && state.userAvatar.startsWith('data:')) {
        avatarEl.innerHTML = `<img src="${state.userAvatar}" style="width:100%;height:100%;border-radius:50%;object-fit:cover">`;
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
    if (modal) gsap.fromTo(modal, { scale: 0.85, opacity: 0, y: 16 }, { scale: 1, opacity: 1, y: 0, duration: 0.35, ease: "back.out(1.4)" });
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
    safeStorage.set('RE_LIFE_USER_AVATAR', emoji);
    updateHeaderUI();
    // Save to Firebase
    if (state.userKey || state.userId) {
        FB.saveUserData(state.userKey || state.userId, { photoUrl: emoji });
    }
    closeModal();
}

function handleLogout() {
    if (!state.currentUser) return;
    showConfirm(tr('confirmLogout'), () => {
        state.currentUser = null;
        state.userAvatar = '👤';
        safeStorage.remove('RE_LIFE_CURRENT_USER');
        safeStorage.remove('RE_LIFE_USER_AVATAR');
        window.location.replace('/login');
    });
}

function toggleLogin() {
    if (state.currentUser) {
        showConfirm(tr('confirmLogout'), () => {
            state.currentUser = null;
            state.userAvatar = '👤';
            safeStorage.remove('RE_LIFE_CURRENT_USER');
            safeStorage.remove('RE_LIFE_USER_AVATAR');
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
                    onclick="loginAs('${u.displayName}','${u.photoUrl || '👤'}','${u.id}')">
                <span style="font-size:20px">${u.photoUrl || '👤'}</span>
                <span>${u.displayName}</span>
            </button>
        `).join('');
        document.getElementById('modal-body').innerHTML = list;
        document.getElementById('modal-actions').innerHTML =
            `<button class="btn btn--outline btn--full" onclick="closeModal()">${tr('cancelBtn')}</button>`;
        document.getElementById('modal-overlay').classList.add('is-shown');
    } catch (_) { /* offline */ }
}

async function loginAs(name, avatar, userId) {
    state.currentUser = name;
    state.userAvatar = avatar;
    state.userId = userId || null;
    safeStorage.set('RE_LIFE_CURRENT_USER', name);
    safeStorage.set('RE_LIFE_USER_AVATAR', avatar);
    try {
        const user = await FB.getUserByName(name);
        if (user) {
            state.userId = user.id;
            state.userKey = user._key || null;
            state.spentPoints = user.spent_points || 0;
            state.earnedPoints = user.earned_points || 0;
            state.claimedCoupons = user.claimed_coupons || [];
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

async function handleLogin(e) {
    e.preventDefault();
    const errorEl = document.getElementById('login-error');
    const btn = document.getElementById('login-submit-btn');
    errorEl.textContent = '';
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    if (!username) {
        errorEl.textContent = loginLang === 'zh' ? '請輸入用戶名' : 'Please enter a username';
        return;
    }
    if (!password) {
        errorEl.textContent = loginLang === 'zh' ? '請輸入密碼' : 'Please enter a password';
        return;
    }
    btn.textContent = '...';
    try {
        const user = await FB.loginUser(username, password);
        safeStorage.set('RE_LIFE_CURRENT_USER', user.displayName);
        safeStorage.set('RE_LIFE_USER_AVATAR', user.photoUrl || '👤');
        window.location.replace('/');
    } catch (err) {
        if (err.message === 'USER_NOT_FOUND') {
            errorEl.textContent = loginLang === 'zh' ? '用戶不存在，請先註冊' : 'User not found. Please register first.';
        } else if (err.message === 'WRONG_PASSWORD') {
            errorEl.textContent = loginLang === 'zh' ? '密碼錯誤' : 'Wrong password.';
        } else {
            errorEl.textContent = STRINGS[loginLang].loginError;
        }
    }
    btn.innerHTML = '<span>' + STRINGS[loginLang].loginBtn + '</span>';
}

async function handleRegister(e) {
    e.preventDefault();
    const errorEl = document.getElementById('register-error');
    const btn = document.getElementById('register-submit-btn');
    errorEl.textContent = '';
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    if (!username || username.length < 2) {
        errorEl.textContent = loginLang === 'zh' ? '用戶名至少需要2個字符' : 'Username must be at least 2 characters';
        return;
    }
    if (!password || password.length < 4) {
        errorEl.textContent = loginLang === 'zh' ? '密碼至少需要4個字符' : 'Password must be at least 4 characters';
        return;
    }
    btn.textContent = '...';
    try {
        const user = await FB.createUser(username, password);
        safeStorage.set('RE_LIFE_CURRENT_USER', user.displayName);
        safeStorage.set('RE_LIFE_USER_AVATAR', '👤');
        window.location.replace('/');
    } catch (err) {
        if (err.message === 'USERNAME_TAKEN') {
            errorEl.textContent = loginLang === 'zh' ? '用戶名已被使用' : 'Username already taken';
        } else if (err.message && err.message.includes('permission')) {
            errorEl.textContent = 'Firestore permissions error — check security rules';
        } else {
            errorEl.textContent = (err.message || STRINGS[loginLang].registerError);
        }
    }
    btn.innerHTML = '<span>' + STRINGS[loginLang].createAccountBtn + '</span>';
}

// ═══════════════════════════════════════════════════════════════════════
// 15. LANGUAGE
// ═══════════════════════════════════════════════════════════════════════

async function toggleLang() {
    state.lang = state.lang === 'en' ? 'zh' : 'en';
    safeStorage.set('RE_LIFE_LANG', state.lang);
    if (typeof I18N !== 'undefined') await I18N.load(state.lang);
    document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-HK';
    const langInd = document.getElementById('lang-ind');
    if (langInd) langInd.textContent = state.lang === 'en' ? 'Eng' : '中文';
    updateAllLabels();
    if (state.activeTab === 'record') renderRecords();
    if (state.activeTab === 'rewards') renderRewards();
}

function updateAllLabels() {
    // Map of element IDs → translation keys
    const map = {
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
        'ws-toggle-btn': 'showDetails',
        'lbl-overall': 'overallScore',
        'lbl-grade': 'grade',
        'lbl-advice': 'advice',
        'lbl-dg-title': 'disposalGuide',
        'lbl-disp-material': 'material',
        'lbl-disp-method': 'method',
        'lbl-disp-location': 'location',
        'lbl-fact-title': 'didYouKnow',
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
        'lbl-swap': 'swapMe',
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
// 16. SETTINGS
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
    const icon = document.getElementById('theme-icon');
    if (icon) icon.src = theme === 'dark' ? '/static/assets/DarkMode_Off.png' : '/static/assets/DarkMode_On.png';
    const label = document.getElementById('theme-label');
    if (label) label.textContent = theme === 'dark' ? tr('lightMode') : tr('darkMode');
    safeStorage.set('RE_LIFE_THEME', theme);
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

// ═══════════════════════════════════════════════════════════════════════
// THEME SYSTEM — just sets data-theme; colors defined in CSS
// ═══════════════════════════════════════════════════════════════════════

function initTheme() {
    const saved = safeStorage.get('RE_LIFE_THEME') || 'light';
    applyTheme(saved);
    const sel = document.getElementById('theme-select');
    if (sel) sel.value = saved;
}

function applyTheme(name) {
    document.documentElement.setAttribute('data-theme', name);
    safeStorage.set('RE_LIFE_THEME', name);
    const sel = document.getElementById('theme-select');
    if (sel) sel.value = name;
}
