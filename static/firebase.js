/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Firebase Realtime Database Helpers
   Attached to window.FB for use by app.js (non-module).
   Schema: users | items | suggestions | itemSuggestions
   Passwords hashed with Argon2id + random salt via hash-wasm.
   ═══════════════════════════════════════════════════════════════════════ */

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.14.0/firebase-app.js";
import {
    getDatabase, ref, push, set, get, update, remove,
    query, orderByChild, equalTo, limitToFirst,
} from "https://www.gstatic.com/firebasejs/12.14.0/firebase-database.js";

// argon2id via hash-wasm (WASM, ~20KB gzipped)
import { argon2id, argon2Verify } from "https://cdn.jsdelivr.net/npm/hash-wasm@4/+esm";

const firebaseConfig = {
    apiKey: "AIzaSyCgks1-HcpZVFpjJX6CVlNb-JCKCg9Y6q8",
    authDomain: "re-life-9123f.firebaseapp.com",
    projectId: "re-life-9123f",
    storageBucket: "re-life-9123f.firebasestorage.app",
    messagingSenderId: "246213132121",
    appId: "1:246213132121:web:b2a4580f2582f825ff1648",
    databaseURL: "https://re-life-9123f-default-rtdb.asia-southeast1.firebasedatabase.app",
};

const app = initializeApp(firebaseConfig);
const db = getDatabase(app);

// ═══════════════════════════════════════════════════════════════════════
// PASSWORD HASHING  (Argon2id + random salt)
// ═══════════════════════════════════════════════════════════════════════

function randomSalt(length = 16) {
    const bytes = new Uint8Array(length);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password, salt) {
    // argon2id(t) memory=64MB, parallelism=1, iterations=3, hashLen=32
    return await argon2id({
        password,
        salt,
        parallelism: 1,
        iterations: 3,
        memorySize: 65536,  // 64 MB
        hashLength: 32,
        outputType: "encoded",  // $argon2id$v=19$m=65536,t=3,p=1$salt$hash
    });
}

async function verifyPassword(password, storedHash) {
    // Use hash-wasm's built-in argon2Verify — handles PHC string parsing correctly
    try {
        return await argon2Verify({ password, hash: storedHash });
    } catch {
        return false;
    }
}

// ═══════════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════════

const FB = {

    // ── Users ──────────────────────────────────────────────────────────

    async createUser(displayName, password, email = null) {
        // Check if username already taken
        const qName = query(ref(db, "users"), orderByChild("displayName"), equalTo(displayName), limitToFirst(1));
        const snapName = await get(qName);
        if (snapName.exists()) throw new Error("USERNAME_TAKEN");

        // Check if email already registered
        if (email) {
            const qEmail = query(ref(db, "users"), orderByChild("email"), equalTo(email), limitToFirst(1));
            const snapEmail = await get(qEmail);
            if (snapEmail.exists()) throw new Error("EMAIL_TAKEN");
        }

        const salt = randomSalt();
        const passwordHash = await hashPassword(password, salt);
        // Short unique user ID: "usr_" + 8 hex chars from UUID v4
        const userId = "usr_" + crypto.randomUUID().split("-")[0];
        const userRef = push(ref(db, "users"));
        await set(userRef, {
            userId,
            displayName,
            passwordHash,
            email: email || null,
            emailVerified: !!email,
            createdAt: Date.now(),
            photoUrl: null,
        });
        return { id: userId, displayName };
    },

    async getUserById(userId) {
        const q = query(ref(db, "users"), orderByChild("userId"), equalTo(userId), limitToFirst(1));
        const snap = await get(q);
        if (!snap.exists()) return null;
        const entries = Object.entries(snap.val());
        if (entries.length === 0) return null;
        const [id, data] = entries[0];
        return { id: data.userId, ...data };
    },

    async getUserByName(displayName) {
        const q = query(ref(db, "users"), orderByChild("displayName"), equalTo(displayName), limitToFirst(1));
        const snap = await get(q);
        if (!snap.exists()) return null;
        const entries = Object.entries(snap.val());
        if (entries.length === 0) return null;
        const [id, data] = entries[0];
        return { id, ...data };
    },

    async loginUser(displayName, password) {
        const user = await FB.getUserByName(displayName);
        if (!user) throw new Error("USER_NOT_FOUND");
        const ok = await verifyPassword(password, user.passwordHash);
        if (!ok) throw new Error("WRONG_PASSWORD");
        return { id: user.userId || user.id, displayName: user.displayName, photoUrl: user.photoUrl };
    },

    async getAllUsers() {
        const snap = await get(ref(db, "users"));
        if (!snap.exists()) return [];
        const val = snap.val();
        return Object.entries(val).map(([firebaseKey, data]) => {
            const { passwordHash, ...safe } = data;
            return { id: data.userId || firebaseKey, ...safe };
        });
    },

    async getUser(userId) {
        const snap = await get(ref(db, "users/" + userId));
        if (!snap.exists()) return null;
        const data = snap.val();
        const { passwordHash, ...safe } = data;
        return { id: userId, ...safe };
    },

    async saveUserData(userId, data) {
        await update(ref(db, "users/" + userId), data);
    },

    // ── Items ──────────────────────────────────────────────────────────

    async addItem(item) {
        const itemRef = push(ref(db, "items"));
        await set(itemRef, {
            name: item.name || "Scanned Item",
            createdAt: Date.now(),
            status: item.mode || "dispose",
            description: item.description || "",
            photoUrl: item.image_url || "",
            dealtWithMethod: item.disposal_guide || "",
            dealtWithDate: null,
            user: item.userName || null,
            eco_rate: item.eco_rate || 3,
            recycle_rate: item.recycle_rate || 4,
            overall_score: item.overall_score || 50,
            material: item.material || "",
            grade: item.grade || "",
            brand: item.brand || "",
            category: item.category || "",
            weighted_scores: item.weighted_scores || {},
            schema_id: item.schema_id || "",
            alternative: item.alternative || null,
        });
        return { id: itemRef.key };
    },

    async getItems() {
        const snap = await get(query(ref(db, "items"), orderByChild("createdAt")));
        if (!snap.exists()) return [];
        const val = snap.val();
        return Object.entries(val)
            .map(([id, data]) => ({ id, ...data }))
            .reverse();
    },

    async deleteItem(itemId) {
        await remove(ref(db, "items/" + itemId));
    },

    async clearAllItems() {
        const snap = await get(ref(db, "items"));
        if (snap.exists()) {
            const val = snap.val();
            await Promise.all(Object.keys(val).map(id => remove(ref(db, "items/" + id))));
        }
    },

};

window.FB = FB;
