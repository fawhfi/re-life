/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Firebase Realtime Database Helpers
   Attached to window.FB for use by app.js (non-module).
   Config fetched from server (/api/config) — set via Vercel env vars.
   ═══════════════════════════════════════════════════════════════════════ */

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.14.0/firebase-app.js";
import {
    getDatabase, ref, push, set, get, update, remove,
    query, orderByChild, equalTo, limitToFirst,
} from "https://www.gstatic.com/firebasejs/12.14.0/firebase-database.js";

import { argon2id, argon2Verify } from "https://cdn.jsdelivr.net/npm/hash-wasm@4/+esm";

// ═══════════════════════════════════════════════════════════════════════
// INIT  (async — fetches config from server)
// ═══════════════════════════════════════════════════════════════════════

let db = null;

async function initFB() {
    if (db) return;
    const config = window.FIREBASE_CONFIG || {};
    const app = initializeApp(config);
    db = getDatabase(app);
    console.log("[FB] Initialized");
}

// ═══════════════════════════════════════════════════════════════════════
// PASSWORD HASHING  (Argon2id + random salt)
// ═══════════════════════════════════════════════════════════════════════

function randomSalt(length = 16) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password, salt) {
    return await argon2id({
        password, salt,
        parallelism: 1, iterations: 3, memorySize: 65536, hashLength: 32,
        outputType: "encoded",
    });
}

async function verifyPassword(password, storedHash) {
    try { return await argon2Verify({ password, hash: storedHash }); }
    catch { return false; }
}

// ═══════════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════════

const FB = {

    async _ensure() { if (!db) await initFB(); },

    // ── Users ──────────────────────────────────────────────────────────

    async createUser(displayName, password, email = null) {
        await FB._ensure();
        const qName = query(ref(db, "users"), orderByChild("displayName"), equalTo(displayName), limitToFirst(1));
        const snapName = await get(qName);
        if (snapName.exists()) throw new Error("USERNAME_TAKEN");
        if (email) {
            const qEmail = query(ref(db, "users"), orderByChild("email"), equalTo(email), limitToFirst(1));
            const snapEmail = await get(qEmail);
            if (snapEmail.exists()) throw new Error("EMAIL_TAKEN");
        }
        const salt = randomSalt();
        const passwordHash = await hashPassword(password, salt);
        const userId = "usr_" + crypto.randomUUID().split("-")[0];
        const userRef = push(ref(db, "users"));
        await set(userRef, {
            userId, displayName, passwordHash,
            email: email || null, emailVerified: !!email,
            createdAt: Date.now(), photoUrl: null,
            spent_points: 0, earned_points: 0, claimed_coupons: [],
        });
        return { id: userId, displayName };
    },

    async getUserById(userId) {
        await FB._ensure();
        const q = query(ref(db, "users"), orderByChild("userId"), equalTo(userId), limitToFirst(1));
        const snap = await get(q);
        if (!snap.exists()) return null;
        const entries = Object.entries(snap.val());
        if (entries.length === 0) return null;
        const [id, data] = entries[0];
        return { id: data.userId, ...data };
    },

    async getUserByName(displayName) {
        await FB._ensure();
        const q = query(ref(db, "users"), orderByChild("displayName"), equalTo(displayName), limitToFirst(1));
        const snap = await get(q);
        if (!snap.exists()) return null;
        const entries = Object.entries(snap.val());
        if (entries.length === 0) return null;
        const [id, data] = entries[0];
        return { id, ...data };
    },

    async loginUser(displayName, password) {
        await FB._ensure();
        const user = await FB.getUserByName(displayName);
        if (!user) throw new Error("USER_NOT_FOUND");
        const ok = await verifyPassword(password, user.passwordHash);
        if (!ok) throw new Error("WRONG_PASSWORD");
        return { id: user.userId || user.id, displayName: user.displayName, photoUrl: user.photoUrl };
    },

    async resetPasswordByEmail(email, newPassword) {
        await FB._ensure();
        const q = query(ref(db, "users"), orderByChild("email"), equalTo(email), limitToFirst(1));
        const snap = await get(q);
        if (!snap.exists()) throw new Error("USER_NOT_FOUND");
        const entries = Object.entries(snap.val());
        if (entries.length === 0) throw new Error("USER_NOT_FOUND");
        const [key, userData] = entries[0];
        const salt = userData.displayName;
        const passwordHash = await hashPassword(newPassword, salt);
        await update(ref(db, `users/${key}`), { passwordHash });
        return true;
    },

    async getAllUsers() {
        await FB._ensure();
        const snap = await get(ref(db, "users"));
        if (!snap.exists()) return [];
        const val = snap.val();
        return Object.entries(val).map(([firebaseKey, data]) => {
            const { passwordHash, ...safe } = data;
            return { id: data.userId || firebaseKey, ...safe };
        });
    },

    async getUser(userId) {
        await FB._ensure();
        const snap = await get(ref(db, "users/" + userId));
        if (!snap.exists()) return null;
        const data = snap.val();
        const { passwordHash, ...safe } = data;
        return { id: userId, ...safe };
    },

    async saveUserData(userId, data) {
        await FB._ensure();
        await update(ref(db, "users/" + userId), data);
    },

    // ── Items ──────────────────────────────────────────────────────────

    async addItem(item) {
        await FB._ensure();
        const itemRef = push(ref(db, "items"));
        await set(itemRef, {
            name: item.name || "Scanned Item", createdAt: Date.now(),
            status: item.mode || "dispose", description: item.description || "",
            photoUrl: item.image_url || "", dealtWithMethod: item.disposal_guide || "",
            dealtWithDate: null, userId: item.userId || null,
            eco_rate: item.eco_rate || 3, recycle_rate: item.recycle_rate || 4,
            overall_score: item.overall_score || 50, material: item.material || "",
            grade: item.grade || "", brand: item.brand || "", category: item.category || "",
            weighted_scores: item.weighted_scores || {}, schema_id: item.schema_id || "",
            alternative: item.alternative || null,
        });
        return { id: itemRef.key };
    },

    async getItems(userId = null) {
        await FB._ensure();
        const snap = await get(query(ref(db, "items"), orderByChild("createdAt")));
        if (!snap.exists()) return [];
        let items = Object.entries(snap.val()).map(([id, data]) => ({ id, ...data })).reverse();
        if (userId) items = items.filter(it => it.userId === userId);
        return items;
    },

    async deleteItem(itemId) {
        await FB._ensure();
        await remove(ref(db, "items/" + itemId));
    },

    async clearAllItems() {
        await FB._ensure();
        const snap = await get(ref(db, "items"));
        if (snap.exists()) {
            await Promise.all(Object.keys(snap.val()).map(id => remove(ref(db, "items/" + id))));
        }
    },

};

window.FB = FB;
