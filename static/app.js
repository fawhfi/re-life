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

// -- i18n strings (English / 中文) -------------------------------------
const STRINGS = {
    en: {
        appTitle: 'Re-Life', scanItems: 'Scan Your Item',
        navHome: 'Home',
        toDispose: 'TO DISPOSE', toPurchase: 'TO PURCHASE',
        disposeSub: 'E-waste, Organics, Bulky', purchaseSub: 'Groceries, Dairy, Bottles',
        recordHome: 'Record', greenTips: 'GREEN TIPS', knowMore: '+ KNOW MORE',
        ecoRate: 'Eco-Rate', recycleRate: 'Recycle Rate',
        alternativeProduct: 'Alternative Product', addToRecord: 'Add to Record',
        scanAgain: 'Scan Again', uploadPhoto: 'Tap to scan', orDrag: 'or drag & drop anywhere',
        scanning: 'AI Analyzing...', scanningHint: 'Gemini is evaluating your item',
        purchaseMode: '🥛 Purchase Mode', disposalMode: '♻️ Disposal Mode',
        noRecords: 'No records yet', noRecordsHint: 'Start by scanning an item',
        language: 'Language', policy: 'Policy',
        aiModeLabel: '🤖 Gemini AI', aiModeOn: 'Live AI', aiModeOff: 'Mock',
        itemType: 'Item Type', itemState: 'State',
        foodItems: 'Food Items', generalItems: 'General Items',
        newPurchase: 'New Purchase', aboutToExpire: 'About to Expire',
        overallScore: 'Overall Score', grade: 'Grade', advice: 'Advice',
        criteria: 'Weighted Criteria', showDetails: 'Show Details', hideDetails: 'Hide Details',
        disposalGuide: 'Disposal Guide', material: 'Material', method: 'Method',
        location: 'Location', precaution: 'Precaution',
        scanBtn: '🔍 Scan Item', disposeBadge: 'TO DISPOSE', purchaseBadge: 'TO PURCHASE',
        ecoGradeLabel: 'Eco Grade', rewards: 'Rewards', more: 'More',
        pointsBalance: 'Eco Points Balance', pointsAvail: 'Points available',
        rewardsSub: 'Convert your choices into real-world action.',
        myCoupons: 'My Coupons', viewClaimed: '🎫 View Claimed', redeem: 'Redeem',
        ecoMarketplace: 'Eco-Marketplace', claimedCoupons: 'My Claimed Coupons',
        insufficientPoints: 'Not enough points.', swapMe: 'SWAP ME',
        didYouKnow: 'Did you know?', totalItems: 'Items', ecoAvg: 'Eco Avg',
        recycleAvg: 'Recycle Avg', notLoggedIn: 'Not Logged In', logout: 'Logout',
        loginAs: 'Login as', confirmLogout: 'Logout and clear local data?',
        confirmClear: 'Clear all records?', settings: 'Settings',
        soundOn: 'Sound ON', soundOff: 'Sound OFF',
        ecoCommitments: 'My Eco Commitments',
        commitment1: 'Bring reusable tote bag on grocery trips.',
        commitment2: 'Separate compost scraps from general trash.',
        commitment3: 'Consume plant-based milk alternatives weekly.',
        privacyPolicy: 'Privacy & Community Policy',
        policyText: 'Re-Life is committed to preserving local smart waste databases.',
        version: 'Version 4.2.0 (Hong Kong HQ)', fullPolicy: 'Full Policy →',
        clearAll: 'Clear All', couponClaimed: 'Coupon Claimed!',
        couponCode: 'Your coupon code:', couponExpiry: 'Valid 30 days',
        closeBtn: 'Close', cancelBtn: 'Cancel', confirmBtn: 'Confirm',
        loginTitle: 'Welcome Back', loginTagline: 'Green Living Assistant',
        usernameLabel: 'Username', passwordLabel: 'Password',
        loginBtn: 'Log In', registerBtn: 'Create Account',
        createAccountBtn: 'Create Account', backToLogin: '← Back to Login',
        orDivider: 'or', versionLabel: 'v4.2.0 HK',
        regUsernameLabel: 'Choose Username', regPasswordLabel: 'Choose Password',
        loginError: 'Login failed. Try again.', registerError: 'Registration failed.',
        usernameTaken: 'Username already taken.',
    },
    zh: {
        appTitle: 'Re-Life', scanItems: '主頁',
        toDispose: '要丟棄', toPurchase: '要購買',
        disposeSub: '電子廢物、有機物、大型物品', purchaseSub: '雜貨、乳製品、瓶裝',
        recordHome: '記錄', greenTips: '綠色提示', knowMore: '+ 了解更多',
        ecoRate: '環保評分', recycleRate: '回收率',
        alternativeProduct: '替代產品', addToRecord: '加入記錄',
        scanAgain: '再次掃描', uploadPhoto: '點擊掃描', orDrag: '或拖放檔案到此處',
        scanning: 'AI 分析中...', scanningHint: 'Gemini 正在評估你的物品',
        purchaseMode: '🥛 購買模式', disposalMode: '♻️ 棄置模式',
        noRecords: '尚無記錄', noRecordsHint: '在上方掃描物品開始使用',
        language: '語言', policy: '政策',
        aiModeLabel: '🤖 Gemini AI', aiModeOn: '即時 AI', aiModeOff: '模擬',
        itemType: '物品類型', itemState: '狀態',
        foodItems: '食物類', generalItems: '一般物品',
        newPurchase: '新購買', aboutToExpire: '即將過期',
        overallScore: '總體評分', grade: '等級', advice: '建議',
        criteria: '權重指標', showDetails: '顯示詳情', hideDetails: '隱藏詳情',
        disposalGuide: '棄置指引', material: '物料', method: '處理方法',
        location: '回收地點', precaution: '注意事項',
        scanBtn: '🔍 掃描物品', disposeBadge: '要棄置', purchaseBadge: '要購買',
        ecoGradeLabel: '環保等級', rewards: '獎勵', more: '更多',
        pointsBalance: '環保積分餘額', pointsAvail: '可用積分',
        rewardsSub: '將你的可持續選擇轉化為實際行動。',
        myCoupons: '我的禮券', viewClaimed: '🎫 查看已兌換', redeem: '兌換',
        ecoMarketplace: '環保市集', claimedCoupons: '已兌換禮券',
        insufficientPoints: '積分不足。', swapMe: '更換',
        didYouKnow: '你知道嗎？', totalItems: '物品數', ecoAvg: '環保均分',
        recycleAvg: '回收均分', notLoggedIn: '尚未登入', logout: '登出',
        loginAs: '登入為', confirmLogout: '確定登出並清除本地數據？',
        confirmClear: '確定清除所有記錄？', settings: '設置',
        soundOn: '聲音開', soundOff: '靜音',
        ecoCommitments: '我的環保承諾',
        commitment1: '購物時攜帶可重複使用的帆布袋。',
        commitment2: '將廚餘與一般垃圾分開。',
        commitment3: '每週飲用植物奶替代品。',
        privacyPolicy: '隱私與社區政策',
        policyText: 'Re-Life 致力於保護本地智慧廢物數據庫。',
        version: '版本 4.2.0 (香港總部)', fullPolicy: '完整政策 →',
        clearAll: '清除全部', couponClaimed: '禮券已領取！',
        couponCode: '你的禮券代碼：', couponExpiry: '有效期 30 天',
        closeBtn: '關閉', cancelBtn: '取消', confirmBtn: '確認',
        loginTitle: '歡迎回來', loginTagline: '綠色生活助手',
        usernameLabel: '用戶名', passwordLabel: '密碼',
        loginBtn: '登入', registerBtn: '建立帳戶',
        createAccountBtn: '建立帳戶', backToLogin: '← 返回登入',
        orDivider: '或', versionLabel: 'v4.2.0 香港',
        regUsernameLabel: '選擇用戶名', regPasswordLabel: '選擇密碼',
        loginError: '登入失敗，請重試。', registerError: '註冊失敗。',
        usernameTaken: '用戶名已被使用。',
    },
};


// ═══════════════════════════════════════════════════════════════════════
// 2. UTILITIES
// ═══════════════════════════════════════════════════════════════════════

function tr(key) {
    return STRINGS[state.lang][key] || key;
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
        h += `<span class="star ${i <= r ? 'is-filled' : ''}">★</span>`;
    }
    h += `<span class="rating-value">${r}/5</span>`;
    return h;
}

function renderStars(id, rating) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = buildStars(rating);
}

function calcWeighted(scores, schemaId) {
    const w = SCHEMA_WEIGHTS[schemaId] || SCHEMA_WEIGHTS.food_new;
    return Math.round(
        (scores.a || 50) * w.a +
        (scores.b || 50) * w.b +
        (scores.c || 50) * w.c +
        (scores.d || 50) * w.d +
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

// safeStorage: localStorage with in-memory fallback
const safeStorage = {
    _mem: {},
    get(k) {
        try { return localStorage.getItem(k); } catch { return this._mem[k] || null; }
    },
    set(k, v) {
        try { localStorage.setItem(k, String(v)); } catch { this._mem[k] = String(v); }
    },
    remove(k) {
        try { localStorage.removeItem(k); } catch { delete this._mem[k]; }
    },
};


// ── Number counting animation utility ─────────────────────────────────
function animateNumber(elementId, start, end, duration = 800) {
    const obj = document.getElementById(elementId);
    if (!obj) return;
    
    // If value didn't change, just set it
    if (start === end) {
        obj.textContent = end;
        return;
    }

    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // easeOutQuint easing for decelerating count-up
        const easeProgress = 1 - Math.pow(1 - progress, 5);
        const currentCount = Math.floor(easeProgress * (end - start) + start);
        
        obj.textContent = currentCount.toLocaleString();
        
        if (progress < 1) {
            window.requestAnimationFrame(step);
        } else {
            obj.textContent = end.toLocaleString();
        }
    };
    window.requestAnimationFrame(step);
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
    claimedCoupons: [],
    rewards: [],
    clockInterval: null,
    debugMode: false,
};


// ═══════════════════════════════════════════════════════════════════════
// 4. SOUND EFFECTS
// ═══════════════════════════════════════════════════════════════════════

let soundOn = true;

function playBeep(type) {
    if (!soundOn) return;
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        if (type === 'success') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(523, ctx.currentTime);
            osc.frequency.setValueAtTime(659, ctx.currentTime + 0.1);
            osc.frequency.setValueAtTime(1046, ctx.currentTime + 0.3);
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            osc.start();
            osc.stop(ctx.currentTime + 0.45);
        } else if (type === 'error') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(180, ctx.currentTime);
            gain.gain.setValueAtTime(0.1, ctx.currentTime);
            osc.start();
            osc.stop(ctx.currentTime + 0.2);
        } else {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            osc.start();
            osc.stop(ctx.currentTime + 0.12);
        }
    } catch (_) {
        /* AudioContext unavailable */
    }
}


// ═══════════════════════════════════════════════════════════════════════
// 5. INITIALIZATION
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

    startClock();
    await initAccounts();
    await loadRecords();
    loadTips();
    loadRewards();
    loadFact();
    setupDragDrop();
    await detectCamera();
    initTheme();
    setScanModeUI('dispose'); // default active scan button
    updateAllLabels();
    updateHeaderUI();
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
// 6. TAB NAVIGATION
// ═══════════════════════════════════════════════════════════════════════

function navigateTo(name) {
    state.activeTab = name;
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('is-active'));
    const tab = document.getElementById(`tab-${name}`);
    const nav = document.getElementById(`nav-${name}`);
    if (tab) tab.classList.add('active');
    if (nav) nav.classList.add('is-active');
    if (name === 'record') loadRecords();
    if (name === 'rewards') renderRewards();
    if (name === 'more') {
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
    if (active) active.classList.add('scan-btn--active');
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
        zone.classList.add('drag-over');
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
    document.getElementById('upload-preview-img').src = dataUrl;
    document.getElementById('upload-preview').classList.add('is-shown');
}

function clearPreview() {
    state.selectedFile = null;
    document.getElementById('upload-preview').classList.remove('is-shown');
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

    document.getElementById('scan-status').classList.add('is-shown');
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
        // Fall back to on-device CNN classifier
        try {
            const arrayBuf = await state.selectedFile.arrayBuffer();
            const aiResult = await CLASSIFIER.analyze(arrayBuf, state.scanMode);
            
            aiResult.mode = state.scanMode;
            aiResult.schema_id = `${state.itemType}_${state.itemState}`;
            aiResult.weighted_scores = aiResult.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 };
            aiResult.overall_score = calcWeighted(aiResult.weighted_scores, aiResult.schema_id);
            const g = getGrade(aiResult.overall_score);
            aiResult.grade = g.grade;
            aiResult.grade_advice = g.advice;
            aiResult.grade_color = g.color;
            aiResult.criteria_labels = CRITERIA_LABELS[aiResult.schema_id];
            aiResult.image_url = document.getElementById('upload-preview-img').src;
            
            showScanResult(aiResult);
            playBeep('success');
        } catch (clsErr) {
            console.error('Classifier fallback also failed:', clsErr);
            const msg = (clsErr.message || String(clsErr));
            document.getElementById('scan-result').classList.remove('hidden');
            document.getElementById('result-name').textContent = 'Scan Error';
            document.getElementById('result-desc').textContent = msg;
            document.getElementById('result-brand').textContent = '';
            document.getElementById('gemini-error').textContent = '❌ ' + msg;
            document.getElementById('gemini-error').style.display = 'block';
            playBeep('error');
        }
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

    // Alternative product
    const alt = document.getElementById('result-alt');
    if (item.alternative) {
        alt.classList.remove('hidden');
        document.getElementById('alt-name').textContent = item.alternative.name;
        renderStars('alt-eco-stars', item.alternative.eco_rate);
        renderStars('alt-recycle-stars', item.alternative.recycle_rate);
    } else {
        alt.classList.add('hidden');
    }

    // Weighted score breakdown
    const schemaId = item.schema_id || 'food_new';
    const overall = item.overall_score ||
        calcWeighted(item.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 }, schemaId);
    const grade = item.grade ? { grade: item.grade, color: item.grade_color } : getGrade(overall);

    document.getElementById('ov-score').textContent = overall;
    document.getElementById('ov-bar-fill').style.cssText = `width:${overall}%;background:${grade.color}`;
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
    delete record.image_url;
    delete record.disposal_info;
    delete record.criteria_labels;
    record.image = state.scanMode === 'purchase' ? '🥛' : '🗑️';

    if (record.overall_score === undefined) {
        record.overall_score = calcWeighted(
            record.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 },
            record.schema_id || 'food_new'
        );
    }

    fetch('/api/records', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
    })
        .then(r => r.json())
        .then(() => {
            resetScan();
            navigateTo('record');
        });
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

function resetScan() {
    clearPreview();
    document.getElementById('scan-result').classList.add('hidden');
    document.getElementById('weighted-detail').classList.remove('is-open');
    state.lastScanResult = null;
}


// ═══════════════════════════════════════════════════════════════════════
// 10. RECORDS
// ═══════════════════════════════════════════════════════════════════════

async function loadRecords() {
    try {
        const res = await fetch('/api/records');
        state.records = await res.json();
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

        return `
        <div class="record-card" id="rec-${r.id}">
            <div class="record-card-inner">
                <div class="record-card-image">${r.image || '📦'}</div>
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
                <button class="btn btn--danger" onclick="deleteRecord('${r.id}')">🗑️</button>
            </div>
        </div>`;
    }).join('');
}

async function deleteRecord(id) {
    try {
        await fetch(`/api/records/${id}`, { method: 'DELETE' });
        const card = document.getElementById(`rec-${id}`);
        if (card) {
            card.style.cssText = 'opacity:0;transform:scale(0.92) translateY(-8px);transition:all 0.3s cubic-bezier(0.4,0,0.2,1)';
            card.style.maxHeight = card.offsetHeight + 'px';
            requestAnimationFrame(() => { card.style.maxHeight = '0px'; card.style.marginTop = '0px'; card.style.marginBottom = '0px'; card.style.paddingTop = '0px'; card.style.paddingBottom = '0px'; card.style.overflow = 'hidden'; });
            setTimeout(loadRecords, 350);
        }
    } catch (e) {
        console.error('Failed to delete record:', e);
    }
}

async function clearAllRecords() {
    showConfirm(tr('confirmClear'), async () => {
        await fetch('/api/records', { method: 'DELETE' });
        state.records = [];
        renderRecords();
        updateStats();
        saveUserData();
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
        const res = await fetch('/api/tips');
        state.tips = await res.json();
        renderTipsDots();
        showTip(0);
    } catch (e) {
        console.error('Failed to load tips:', e);
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
        if (titleEl) titleEl.textContent = `"${tip.title}"`;
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
    // Calculate points balance (purchase mode only)
    const earned = state.records
        .filter(r => r.mode === 'purchase')
        .reduce((s, r) =>
            s + (r.overall_score ||
                calcWeighted(r.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 },
                    r.schema_id || 'food_new')),
            0
        );
    const balance = Math.max(0, earned - state.spentPoints);
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
    const earned = state.records
        .filter(r => r.mode === 'purchase')
        .reduce((s, r) =>
            s + (r.overall_score ||
                calcWeighted(r.weighted_scores || { a: 50, b: 50, c: 50, d: 50, e: 50 },
                    r.schema_id || 'food_new')),
            0
        );
    const balance = Math.max(0, earned - state.spentPoints);
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
    document.getElementById('modal-overlay').classList.add('is-shown');
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
        state.userAvatar = safeStorage.get('RE_LIFE_USER_AVATAR') || '👤';
        try {
            const res = await fetch(`/api/users/${encodeURIComponent(stored)}/data`);
            const data = await res.json();
            state.spentPoints = data.spent_points || 0;
            state.claimedCoupons = data.claimed_coupons || [];
        } catch (_) { /* offline */ }
    }
    updateHeaderUI();
}

function updateHeaderUI() {
    document.getElementById('hdr-avatar').textContent = state.userAvatar;
    document.getElementById('hdr-user').textContent = state.currentUser || tr('notLoggedIn');
    document.getElementById('hdr-user').style.display = state.currentUser ? 'block' : 'none';
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
        const res = await fetch('/api/users');
        const users = await res.json();
        document.getElementById('modal-icon').textContent = '👤';
        document.getElementById('modal-title').textContent = tr('loginAs');
        const list = users.map(u => `
            <button class="btn btn--outline btn--full" style="margin-bottom:6px;justify-content:flex-start;gap:8px"
                    onclick="loginAs('${u.name}','${u.avatar}')">
                <span style="font-size:20px">${u.avatar}</span>
                <span>${u.name}</span>
            </button>
        `).join('');
        document.getElementById('modal-body').innerHTML = list;
        document.getElementById('modal-actions').innerHTML =
            `<button class="btn btn--outline btn--full" onclick="closeModal()">${tr('cancelBtn')}</button>`;
        document.getElementById('modal-overlay').classList.add('is-shown');
    } catch (_) { /* offline */ }
}

async function loginAs(name, avatar) {
    state.currentUser = name;
    state.userAvatar = avatar;
    safeStorage.set('RE_LIFE_CURRENT_USER', name);
    safeStorage.set('RE_LIFE_USER_AVATAR', avatar);
    try {
        const res = await fetch(`/api/users/${encodeURIComponent(name)}/data`);
        const data = await res.json();
        state.spentPoints = data.spent_points || 0;
        state.claimedCoupons = data.claimed_coupons || [];
    } catch (_) { /* offline */ }
    closeModal();
    updateHeaderUI();
    navigateTo('home');
}

async function saveUserData() {
    if (!state.currentUser) return;
    try {
        await fetch(`/api/users/${encodeURIComponent(state.currentUser)}/data`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                spent_points: state.spentPoints,
                claimed_coupons: state.claimedCoupons,
            }),
        });
    } catch (_) { /* offline */ }
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
    if (!username) {
        errorEl.textContent = loginLang === 'zh' ? '請輸入用戶名' : 'Please enter a username';
        return;
    }
    btn.textContent = '...';
    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username }),
        });
        const data = await res.json();
        if (data.ok) {
            safeStorage.set('RE_LIFE_CURRENT_USER', data.user.name);
            safeStorage.set('RE_LIFE_USER_AVATAR', data.user.avatar);
            window.location.replace('/');
        } else {
            errorEl.textContent = data.error || STRINGS[loginLang].loginError;
        }
    } catch (_) {
        errorEl.textContent = STRINGS[loginLang].loginError;
    }
    btn.innerHTML = '<span>' + STRINGS[loginLang].loginBtn + '</span>';
}

async function handleRegister(e) {
    e.preventDefault();
    const errorEl = document.getElementById('register-error');
    const btn = document.getElementById('register-submit-btn');
    errorEl.textContent = '';
    const username = document.getElementById('reg-username').value.trim();
    if (!username || username.length < 2) {
        errorEl.textContent = loginLang === 'zh' ? '用戶名至少需要2個字符' : 'Username must be at least 2 characters';
        return;
    }
    btn.textContent = '...';
    try {
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username }),
        });
        const data = await res.json();
        if (data.ok) {
            safeStorage.set('RE_LIFE_CURRENT_USER', data.user.name);
            safeStorage.set('RE_LIFE_USER_AVATAR', data.user.avatar);
            window.location.replace('/');
        } else {
            errorEl.textContent = data.error || STRINGS[loginLang].registerError;
        }
    } catch (_) {
        errorEl.textContent = STRINGS[loginLang].registerError;
    }
    btn.innerHTML = '<span>' + STRINGS[loginLang].createAccountBtn + '</span>';
}

// ═══════════════════════════════════════════════════════════════════════
// 15. LANGUAGE
// ═══════════════════════════════════════════════════════════════════════

function toggleLang() {
    state.lang = state.lang === 'en' ? 'zh' : 'en';
    document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-HK';
    document.getElementById('lang-ind').textContent = state.lang === 'en' ? 'Eng' : '中文';
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
        'nav-lbl-home': 'navHome',
        'nav-lbl-record': 'recordHome',
        'nav-lbl-rewards': 'rewards',
        'nav-lbl-more': 'more',
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
    if (label) label.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
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
    document.getElementById('debug-btn').textContent = state.debugMode ? '🔧 Debug Mode: ON' : '🔧 Debug Mode: OFF';
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