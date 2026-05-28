/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Client-side ONNX Classifier
   Runs INT8 EfficientNet-B2 model in the browser via ONNX Runtime Web.
   
   Replaces the server-side classifier.py fallback — inference now runs
   entirely on the user's device with zero server GPU/CPU cost.
   ═══════════════════════════════════════════════════════════════════════ */

const CLASSIFIER = (() => {

    // ─── Constants (mirrors classifier.py) ──────────────────────────────
    const CATEGORIES = ["glass", "metal", "organic", "paper", "plastic", "ewaste"];
    const IMG_SIZE   = 260;
    const MEAN       = [0.485, 0.456, 0.406];
    const STD        = [0.229, 0.224, 0.225];

    // ─── Material → response mapping ────────────────────────────────────
    const MATERIAL_MAP = {
        glass: {
            material: "glass", standard_type: "general",
            eco_rate: 4, recycle_rate: 5,
            description: "Glass container — infinitely recyclable without quality loss.",
            disposal_guide: "Rinse clean, remove caps. Place in glass recycling bins.",
            precaution: "Do not mix with broken window glass or mirrors.",
        },
        metal: {
            material: "metal", standard_type: "general",
            eco_rate: 4, recycle_rate: 5,
            description: "Metal can or container — highly recyclable and retains value.",
            disposal_guide: "Rinse clean, flatten if possible. Place in metal recycling bins.",
            precaution: "Remove any plastic lids or labels before recycling.",
        },
        organic: {
            material: "compostable", standard_type: "food",
            eco_rate: 5, recycle_rate: 4,
            description: "Organic / food waste — can be composted or used for biogas.",
            disposal_guide: "Separate from general waste. Use food waste recycling bins.",
            precaution: "Remove any non-compostable packaging before disposal.",
        },
        paper: {
            material: "paper", standard_type: "general",
            eco_rate: 5, recycle_rate: 5,
            description: "Paper or cardboard packaging — biodegradable and widely recycled.",
            disposal_guide: "Keep dry, flatten cardboard. Place in blue paper recycling bins.",
            precaution: "Do not recycle greasy or food-soiled paper.",
        },
        plastic: {
            material: "plastic", standard_type: "general",
            eco_rate: 2, recycle_rate: 3,
            description: "Plastic container or packaging — check resin code for recyclability.",
            disposal_guide: "Rinse clean, flatten. Use tri-colour recycling bins.",
            precaution: "Remove pumps, spray tops, and mixed-material parts.",
        },
        ewaste: {
            material: "ewaste", standard_type: "general",
            eco_rate: 2, recycle_rate: 3,
            description: "Electronic waste — contains recoverable metals but also hazardous materials.",
            disposal_guide: "Take to designated e-waste collection points or WEEE·PARK in HK.",
            precaution: "Remove batteries before disposal. Do not place in regular recycling bins.",
        },
    };

    const NAME_POOL = {
        glass:   ["Glass Bottle", "Glass Jar", "Glass Container"],
        metal:   ["Aluminum Can", "Metal Tin", "Steel Container"],
        organic: ["Food Waste", "Organic Scrap", "Compostable Item"],
        paper:   ["Cardboard Box", "Paper Package", "Paper Carton"],
        plastic: ["Plastic Bottle", "Plastic Container", "Plastic Packaging"],
        ewaste:  ["Electronic Device", "E-Waste Item", "Electronic Component"],
    };

    // ─── State ──────────────────────────────────────────────────────────
    let _session = null;
    let _ready = false;
    let _loading = false;
    let _loadPromise = null;

    const MODEL_URL = '/static/models/model_INT8.onnx';

    // ─── Public API ─────────────────────────────────────────────────────

    /** Returns true once the ONNX session is loaded and ready. */
    function isReady() { return _ready; }

    /** Trigger loading (idempotent — safe to call multiple times). */
    function load() {
        if (_ready) return Promise.resolve(true);
        if (_loadPromise) return _loadPromise;

        _loading = true;
        _loadPromise = (async () => {
            try {
                console.log('[Classifier] Loading ONNX model from', MODEL_URL);
                // Use WASM backend for broadest compatibility
                const session = await ort.InferenceSession.create(MODEL_URL, {
                    executionProviders: ['wasm'],
                    graphOptimizationLevel: 'all',
                });
                _session = session;
                _ready = true;
                console.log('[Classifier] Model loaded — input:', session.inputNames,
                            'output:', session.outputNames);
                return true;
            } catch (e) {
                console.error('[Classifier] Failed to load model:', e);
                _loading = false;
                _loadPromise = null;
                return false;
            }
        })();
        return _loadPromise;
    }

    // ─── Image Preprocessing ────────────────────────────────────────────

    /**
     * Preprocess an image (bytes or Blob/File) into a Float32Array tensor
     * matching the training pipeline: resize → normalize → NCHW.
     */
    async function preprocess(imageSource) {
        // Create an ImageBitmap from the source
        let img;
        if (imageSource instanceof Blob || imageSource instanceof File) {
            img = await createImageBitmap(imageSource, { resizeWidth: IMG_SIZE, resizeHeight: IMG_SIZE });
        } else if (imageSource instanceof ArrayBuffer || imageSource instanceof Uint8Array) {
            const blob = new Blob([imageSource]);
            img = await createImageBitmap(blob, { resizeWidth: IMG_SIZE, resizeHeight: IMG_SIZE });
        } else {
            // Assume it's bytes (Uint8Array)
            const blob = new Blob([imageSource]);
            img = await createImageBitmap(blob, { resizeWidth: IMG_SIZE, resizeHeight: IMG_SIZE });
        }

        // Draw to canvas for pixel extraction
        const canvas = document.createElement('canvas');
        canvas.width = IMG_SIZE;
        canvas.height = IMG_SIZE;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, IMG_SIZE, IMG_SIZE);
        img.close();

        const imageData = ctx.getImageData(0, 0, IMG_SIZE, IMG_SIZE);
        const pixels = imageData.data; // RGBA, Uint8ClampedArray

        // Build NCHW float32 tensor: shape [1, 3, 260, 260] = 202800 elements
        const tensorSize = 1 * 3 * IMG_SIZE * IMG_SIZE;
        const data = new Float32Array(tensorSize);

        for (let y = 0; y < IMG_SIZE; y++) {
            for (let x = 0; x < IMG_SIZE; x++) {
                const srcIdx = (y * IMG_SIZE + x) * 4; // RGBA
                // Normalize: (pixel/255 - mean) / std
                const r = ((pixels[srcIdx]     / 255) - MEAN[0]) / STD[0];
                const g = ((pixels[srcIdx + 1] / 255) - MEAN[1]) / STD[1];
                const b = ((pixels[srcIdx + 2] / 255) - MEAN[2]) / STD[2];

                // NCHW layout: channel c at (c * H * W + y * W + x)
                data[0 * IMG_SIZE * IMG_SIZE + y * IMG_SIZE + x] = r;
                data[1 * IMG_SIZE * IMG_SIZE + y * IMG_SIZE + x] = g;
                data[2 * IMG_SIZE * IMG_SIZE + y * IMG_SIZE + x] = b;
            }
        }

        return data;
    }

    // ─── Softmax ────────────────────────────────────────────────────────

    function softmax(logits) {
        const max = Math.max(...logits);
        const ex = logits.map(v => Math.exp(v - max));
        const sum = ex.reduce((a, b) => a + b, 0);
        return ex.map(v => v / sum);
    }

    // ─── Inference ──────────────────────────────────────────────────────

    /**
     * Run inference and return { category, confidence }.
     * @param {Uint8Array|ArrayBuffer} imageBytes — raw image bytes
     * @returns {{ category: string, confidence: number }}
     */
    async function predict(imageBytes) {
        if (!_ready) {
            const ok = await load();
            if (!ok) throw new Error('Classifier model failed to load');
        }

        const inputData = await preprocess(imageBytes);
        const inputTensor = new ort.Tensor('float32', inputData, [1, 3, IMG_SIZE, IMG_SIZE]);

        const feeds = {};
        feeds[_session.inputNames[0]] = inputTensor;

        const results = await _session.run(feeds);
        const outputName = _session.outputNames[0];
        const logits = results[outputName].data; // Float32Array

        const probs = softmax(Array.from(logits));
        const maxIdx = probs.indexOf(Math.max(...probs));

        return {
            category: CATEGORIES[maxIdx],
            confidence: probs[maxIdx],
        };
    }

    /**
     * Full analysis pipeline — returns the dict format expected by the app.
     * @param {Uint8Array|ArrayBuffer} imageBytes
     * @param {'dispose'|'purchase'} mode
     * @returns {object}
     */
    async function analyze(imageBytes, mode) {
        const { category, confidence } = await predict(imageBytes);
        const info = MATERIAL_MAP[category] || MATERIAL_MAP.plastic;
        const names = NAME_POOL[category] || NAME_POOL.plastic;
        const name = names[Math.floor(Math.random() * names.length)];

        // Derive weighted scores from eco_rate (1-5 → 0-100 scale with noise)
        const eco = info.eco_rate;
        const rec  = info.recycle_rate;
        const base = Math.round(((eco + rec) / 2) * 20);
        const jitter = () => Math.max(0, Math.min(100, base + Math.floor(Math.random() * 25) - 12));

        return {
            name:            name,
            brand:           '',
            category:        category,
            standard_type:   info.standard_type,
            description:     `${info.description} (On-device CNN, ${Math.round(confidence * 100)}% confidence)`,
            material:        info.material,
            disposal_guide:  info.disposal_guide,
            precaution:      info.precaution,
            eco_rate:        eco,
            recycle_rate:    rec,
            weighted_scores: {
                a: jitter(), b: jitter(), c: jitter(), d: jitter(), e: jitter(),
            },
            alternative: mode === 'purchase' ? {
                name:         'Eco-Friendly Alternative (AI fallback)',
                eco_rate:     5,
                recycle_rate: 5,
            } : null,
        };
    }

    // ─── Auto-load ──────────────────────────────────────────────────────
    // Start loading as early as possible (non-blocking)
    load();

    return { isReady, load, predict, analyze };
})();
