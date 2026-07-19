// camera.js — Camera capture module for Re-Life

let cameraStream = null;
let cameraFacing = 'environment'; // 'environment' (rear) or 'user' (front)

async function openCamera() {
    const modal = document.getElementById('camera-modal');
    const video = document.getElementById('camera-video');
    if (!modal || !video) {
        cameraAvailable = false;
        if (typeof openScanSourceDialog === 'function') openScanSourceDialog();
        return;
    }

    modal.classList.add('is-shown');
    document.body.style.overflow = 'hidden';
    gsap.fromTo(modal, { y: '100%' }, { y: 0, duration: 0.3, ease: "power2.out" });
    document.body.classList.add('camera-active');

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
            return;
        } catch (_) {}
    }

    cameraAvailable = false;
    closeCamera();
    if (typeof showToast === 'function') showToast(tr('scanCameraUnavailable'), 'warning');
    if (typeof openScanSourceDialog === 'function') openScanSourceDialog();
}

function closeCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
    document.getElementById('camera-modal').classList.remove('is-shown');
    document.getElementById('camera-video').srcObject = null;
    document.body.style.overflow = '';
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
}

async function detectCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        cameraAvailable = false; return;
    }
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const hasVideo = devices.some(d => d.kind === 'videoinput');
        cameraAvailable = hasVideo;
    } catch (_) {
        cameraAvailable = false;
    }
}
