/* ═══════════════════════════════════════════════════════════════════════
   Re-Life — Firebase / Firestore Helpers
   Attached to window.FB for use by app.js (non-module).
   Schema: users | items | suggestions | itemSuggestions
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

const FB = {

    // ── Users ──────────────────────────────────────────────────────────

    async createUser(displayName) {
        const existing = await FB.getUserByName(displayName);
        if (existing) throw new Error("Username already taken");
        const ref = await addDoc(collection(db, "users"), {
            displayName,
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

    async getAllUsers() {
        const snap = await getDocs(collection(db, "users"));
        return snap.docs.map(d => ({ id: d.id, ...d.data() }));
    },

    async getUser(userId) {
        const d = await getDoc(doc(db, "users", userId));
        if (!d.exists()) return null;
        return { id: d.id, ...d.data() };
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
