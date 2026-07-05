/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — backend storage helper
   Attached to window.FB for use by app.js (legacy interface name only).
   ═══════════════════════════════════════════════════════════════════════ */

function buildUrl(path, params = null) {
    const url = new URL(path, window.location.origin);
    if (params) {
        for (const [key, value] of Object.entries(params)) {
            if (value === undefined || value === null || value === "") continue;
            url.searchParams.set(key, String(value));
        }
    }
    return url;
}

async function requestJson(path, { method = "GET", body = undefined, params = null } = {}) {
    const url = buildUrl(path, params);
    const init = {
        method,
        headers: { Accept: "application/json" },
    };
    if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
    }
    const response = await fetch(url, init);
    const text = await response.text();
    let data = null;
    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            data = { raw: text };
        }
    }
    if (!response.ok) {
        const error = new Error(formatErrorMessage(data, response));
        error.status = response.status;
        error.payload = data;
        throw error;
    }
    return data;
}

async function requestFormJson(path, { method = "POST", body = undefined, params = null } = {}) {
    const url = buildUrl(path, params);
    const response = await fetch(url, {
        method,
        headers: { Accept: "application/json" },
        body,
    });
    const text = await response.text();
    let data = null;
    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            data = { raw: text };
        }
    }
    if (!response.ok) {
        const error = new Error(formatErrorMessage(data, response));
        error.status = response.status;
        error.payload = data;
        throw error;
    }
    return data;
}

function stringifyErrorValue(value) {
    if (value === undefined || value === null || value === "") return "";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) {
        return value.map(stringifyErrorValue).filter(Boolean).join("; ");
    }
    if (typeof value === "object") {
        const parts = [];
        for (const key of ["message", "error", "detail", "details", "hint", "code"]) {
            if (value[key] !== undefined) {
                const text = stringifyErrorValue(value[key]);
                if (text) parts.push(`${key}: ${text}`);
            }
        }
        try {
            const json = JSON.stringify(value);
            if (json && json !== "{}" && !parts.includes(json)) parts.push(json);
        } catch {
            const fallback = String(value);
            if (fallback !== "[object Object]") parts.push(fallback);
        }
        return [...new Set(parts)].join(" | ");
    }
    return String(value);
}

function formatErrorMessage(data, response) {
    const candidate = data && (data.error ?? data.detail ?? data.message ?? data.raw);
    const detail = stringifyErrorValue(candidate) || stringifyErrorValue(data);
    const prefix = `HTTP_${response.status}`;
    return detail ? `${prefix}: ${detail}` : prefix;
}

function safeArray(value) {
    return Array.isArray(value) ? value : [];
}

function normalizeUser(user) {
    if (!user) return null;
    const claimed = safeArray(user.claimed_coupons || user.claimedCoupons);
    const publicId = user.public_id || user.userId || user._key || null;
    return {
        id: user.id ?? publicId,
        public_id: publicId,
        userId: publicId,
        _key: publicId,
        displayName: user.displayName || user.display_name || "",
        display_name: user.display_name || user.displayName || "",
        email: user.email || null,
        photoUrl: user.photoUrl || user.photo_url || null,
        photo_url: user.photo_url || user.photoUrl || null,
        spent_points: user.spent_points ?? user.spentPoints ?? 0,
        spentPoints: user.spent_points ?? user.spentPoints ?? 0,
        earned_points: user.earned_points ?? user.earnedPoints ?? 0,
        earnedPoints: user.earned_points ?? user.earnedPoints ?? 0,
        claimed_coupons: claimed,
        claimedCoupons: claimed,
        emailVerified: !!(user.emailVerified ?? user.email_verified),
    };
}

function normalizeItem(item) {
    if (!item) return null;
    return {
        id: item.id ?? null,
        name: item.name || "Scanned Item",
        status: item.status || item.mode || "dispose",
        createdAt: item.createdAt || item.created_at || Date.now(),
        description: item.description || "",
        photoUrl: item.photoUrl || item.photo_url || item.image_url || null,
        dealtWithMethod: item.dealtWithMethod || item.dealt_with_method || "",
        dealtWithDate: item.dealtWithDate || item.dealt_with_date || null,
        userId: item.userId || item.user_id || null,
        userName: item.userName || item.user_name || null,
        eco_rate: item.eco_rate ?? 3,
        recycle_rate: item.recycle_rate ?? 4,
        overall_score: item.overall_score ?? item.overallScore ?? 0,
        material: item.material || "",
        grade: item.grade || "",
        grade_color: item.grade_color || null,
        grade_advice: item.grade_advice || null,
        brand: item.brand || "",
        category: item.category || "",
        weighted_scores: item.weighted_scores || item.weightedScores || {},
        schema_id: item.schema_id || item.schemaId || "",
        alternative: item.alternative || null,
        precaution: item.precaution || null,
        image_url: item.image_url || item.photoUrl || null,
    };
}

function fallbackUserId() {
    return localStorage.getItem("RE_LIFE_CURRENT_USER_ID") || localStorage.getItem("RE_LIFE_CURRENT_USER_KEY") || "";
}

function fallbackUserName() {
    return localStorage.getItem("RE_LIFE_CURRENT_USER") || "";
}

function isDataImageUrl(value) {
    return typeof value === "string" && /^data:image\/[-+\w.]+;base64,/i.test(value);
}

function imageExtensionForMime(mime) {
    const normalized = String(mime || "").toLowerCase();
    if (normalized === "image/png") return ".png";
    if (normalized === "image/webp") return ".webp";
    if (normalized === "image/gif") return ".gif";
    return ".jpg";
}

function dataUrlToBlob(dataUrl) {
    const match = /^data:(image\/[-+\w.]+);base64,(.*)$/i.exec(dataUrl || "");
    if (!match) throw new Error("Invalid cached image data");
    const mime = match[1].toLowerCase();
    const binary = atob(match[2]);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
    }
    return {
        blob: new Blob([bytes], { type: mime }),
        mime,
    };
}

async function uploadRecordImageIfNeeded(payload) {
    const localImage = payload.image_url || payload.photoUrl || "";
    if (!isDataImageUrl(localImage)) return localImage || "";

    const { blob, mime } = dataUrlToBlob(localImage);
    const form = new FormData();
    form.append("file", blob, `scan-record${imageExtensionForMime(mime)}`);
    form.append("user_id", payload.userId || fallbackUserId() || "");
    form.append("display_name", payload.userName || fallbackUserName() || "");
    form.append("user_key", payload.userKey || fallbackUserId() || "");

    const data = await requestFormJson("/api/records/image", {
        body: form,
    });
    const imageUrl = data?.image_url || "";
    if (!imageUrl) throw new Error("Image upload failed");
    return imageUrl;
}

function buildRecordPayload(item) {
    return {
        mode: item.mode || item.status || "dispose",
        name: item.name || item.waste_label || item.category || "Scanned Item",
        description: item.description || item.text || "",
        image_url: item.image_url || item.photoUrl || "",
        disposal_guide: item.disposal_guide || item.dealtWithMethod || "",
        dealtWithMethod: item.dealtWithMethod || item.disposal_guide || "",
        eco_rate: item.eco_rate ?? 3,
        recycle_rate: item.recycle_rate ?? 4,
        overall_score: item.overall_score ?? item.overallScore ?? 50,
        material: item.material || "",
        grade: item.grade || "",
        brand: item.brand || "",
        category: item.category || "",
        weighted_scores: item.weighted_scores || item.weightedScores || {},
        schema_id: item.schema_id || item.schemaId || "",
        alternative: item.alternative || null,
        precaution: item.precaution || null,
        reuse_tip: item.reuse_tip || item.reuse || "",
        userId: item.userId || fallbackUserId() || null,
        userName: item.userName || fallbackUserName() || null,
        userKey: item.userKey || fallbackUserId() || null,
    };
}

const FB = {
    async _ensure() {
        return true;
    },

    async createUser(displayName, password, email = null) {
        const data = await requestJson("/api/auth/register", {
            method: "POST",
            body: {
                display_name: displayName,
                email,
                password,
            },
        });
        return normalizeUser(data.user);
    },

    async getUserById(userId) {
        const data = await requestJson(`/api/users/by-id/${encodeURIComponent(userId)}`);
        return normalizeUser(data);
    },

    async getUserByName(displayName) {
        const data = await requestJson(`/api/users/by-name/${encodeURIComponent(displayName)}`);
        return normalizeUser(data);
    },

    async getUserByEmail(email) {
        const data = await requestJson(`/api/users/by-email/${encodeURIComponent(email)}`);
        return normalizeUser(data);
    },

    async loginUser(displayName, password) {
        const data = await requestJson("/api/auth/login", {
            method: "POST",
            body: {
                display_name: displayName,
                password,
            },
        });
        return normalizeUser(data.user);
    },

    async resetPasswordByEmail() {
        throw new Error("RESET_PASSWORD_REQUIRES_CODE");
    },

    async getAllUsers() {
        const data = await requestJson("/api/users");
        return safeArray(data).map(normalizeUser);
    },

    async getUser(userId) {
        return FB.getUserById(userId);
    },

    async saveUserData(userId, data) {
        const identifier = userId || fallbackUserId() || fallbackUserName();
        if (!identifier) return false;
        await requestJson(`/api/users/${encodeURIComponent(identifier)}`, {
            method: "PATCH",
            body: data || {},
        });
        return true;
    },

    async addItem(item) {
        const payload = buildRecordPayload(item || {});
        const imageUrl = await uploadRecordImageIfNeeded(payload);
        if (imageUrl) {
            payload.image_url = imageUrl;
        } else {
            delete payload.image_url;
        }
        const data = await requestJson("/api/records", {
            method: "POST",
            body: payload,
        });
        return { id: data.id ?? null, image_url: payload.image_url || "" };
    },

    async getItems(userId = null, displayName = null, userKey = null) {
        if (!userId && !displayName && !userKey) return [];
        const data = await requestJson("/api/records", {
            params: {
                user_id: userId || fallbackUserId() || "",
                display_name: displayName || fallbackUserName() || "",
                user_key: userKey || "",
            },
        });
        return safeArray(data).map(normalizeItem);
    },

    async deleteItem(itemId) {
        await requestJson(`/api/records/${encodeURIComponent(itemId)}`, {
            method: "DELETE",
        });
    },

    async clearAllItems(userId = null, displayName = null, userKey = null) {
        await requestJson("/api/records", {
            method: "DELETE",
            params: {
                user_id: userId || fallbackUserId() || "",
                display_name: displayName || fallbackUserName() || "",
                user_key: userKey || "",
            },
        });
    },
};

window.FB = FB;
