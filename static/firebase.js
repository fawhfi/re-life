/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Firebase / Firestore Helpers
   Attached to window.FB for use by app.js (non-module).
   Schema: users | items | suggestions | itemSuggestions
   Passwords hashed client-side with SHA-256 + username salt.
   ═══════════════════════════════════════════════════════════════════════ */

import { initializeApp } from "https://www.gstatic.com/firebasejs/12.14.0/firebase-app.js";
import {
    getFirestore, collection, doc, addDoc, getDocs, getDoc,
    setDoc, deleteDoc, query, where, orderBy, serverTimestamp,
    limit,
} from "https://www.gstatic.com/firebasejs/12.14.0/firebase-firestore.js";

const firebaseConfig = {
    apiKey: "AIzaSyCgks1-HcpZVFpjJX6CVlNb-JCKCg9Y6q8",
    authDomain: "re-life-9123f.firebaseapp.com",
    projectId: "re-life-9123f",
    storageBucket: "re-life-9123f.firebasestorage.app",
    messagingSenderId: "246213132121",
    appId: "1:246213132121:web:b2a4580f2582f825ff1648",
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// ═══════════════════════════════════════════════════════════════════════
// PASSWORD HASHING  (SHA-256 + username as salt)
// ═══════════════════════════════════════════════════════════════════════

async function hashPassword(password, salt) {
    const encoder = new TextEncoder();
    const data = encoder.encode(password + ":" + salt);
    const hashBuffer = await crypto.subtle.digest("SHA-256", data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

// ═══════════════════════════════════════════════════════════════════════
// PUBLIC API
// ═══════════════════════════════════════════════════════════════════════

const FB = {

    // ── Users ──────────────────────────────────────────────────────────

    async createUser(displayName, password) {
        const existing = await FB.getUserByName(displayName);
        if (existing) throw new Error("USERNAME_TAKEN");
        const passwordHash = await hashPassword(password, displayName);
        const ref = await addDoc(collection(db, "users"), {
            displayName,
            passwordHash,
            email: null,
            createdAt: serverTimestamp(),
            photoUrl: null,
        });
        return { id: ref.id, displayName };
    },

    async getUserByName(displayName) {
        const q = query(collection(db, "users"), where("displayName", "==", displayName), limit(1));
        const snap = await getDocs(q);
        if (snap.empty) return null;
        const d = snap.docs[0];
        return { id: d.id, ...d.data() };
    },

    async loginUser(displayName, password) {
        const user = await FB.getUserByName(displayName);
        if (!user) throw new Error("USER_NOT_FOUND");
        const expectedHash = await hashPassword(password, displayName);
        if (user.passwordHash !== expectedHash) throw new Error("WRONG_PASSWORD");
        return { id: user.id, displayName: user.displayName, photoUrl: user.photoUrl };
    },

    async getAllUsers() {
        const snap = await getDocs(collection(db, "users"));
        return snap.docs.map(d => {
            const data = d.data();
            // Never expose passwordHash to client
            const { passwordHash, ...safe } = data;
            return { id: d.id, ...safe };
        });
    },

    async getUser(userId) {
        const d = await getDoc(doc(db, "users", userId));
        if (!d.exists()) return null;
        const data = d.data();
        const { passwordHash, ...safe } = data;
        return { id: d.id, ...safe };
    },

    async saveUserData(userId, data) {
        await setDoc(doc(db, "users", userId), data, { merge: true });
    },

    // ── Items ──────────────────────────────────────────────────────────

    async addItem(item) {
        const ref = await addDoc(collection(db, "items"), {
            name: item.name || "Scanned Item",
            createdAt: serverTimestamp(),
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
        return { id: ref.id };
    },

    async getItems() {
        const snap = await getDocs(query(collection(db, "items"), orderBy("createdAt", "desc")));
        return snap.docs.map(d => ({ id: d.id, ...d.data() }));
    },

    async deleteItem(itemId) {
        await deleteDoc(doc(db, "items", itemId));
    },

    async clearAllItems() {
        const snap = await getDocs(collection(db, "items"));
        await Promise.all(snap.docs.map(d => deleteDoc(doc(db, "items", d.id))));
    },

};

window.FB = FB;
