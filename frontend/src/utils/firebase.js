// ============================================================================
// Firebase 初始化和工具函数
// ============================================================================

import { initializeApp } from 'firebase/app';
import {
  getDatabase,
  ref,
  push,
  set,
  get,
  update,
  remove,
  query,
  orderByChild,
  equalTo,
  limitToFirst,
} from 'firebase/database';

let app = null;
let db = null;

/**
 * 初始化 Firebase
 * @param {Object} config - Firebase 配置对象
 */
export function initFirebase(config) {
  if (app) {
    console.warn('[Firebase] Already initialized');
    return;
  }

  try {
    app = initializeApp(config);
    db = getDatabase(app);
    console.log('[Firebase] Initialized successfully');
  } catch (error) {
    console.error('[Firebase] Initialization failed:', error);
    throw error;
  }
}

/**
 * 获取 Database 实例
 * @returns {Database} Firebase Database 实例
 */
export function getDB() {
  if (!db) {
    throw new Error('[Firebase] Not initialized. Call initFirebase first.');
  }
  return db;
}

// ============================================================================
// 用户操作
// ============================================================================

/**
 * 通过用户名查找用户
 * @param {string} displayName - 用户名
 * @returns {Promise<Object|null>} 用户对象或 null
 */
export async function getUserByName(displayName) {
  const database = getDB();
  const q = query(
    ref(database, 'users'),
    orderByChild('displayName'),
    equalTo(displayName),
    limitToFirst(1)
  );

  const snapshot = await get(q);
  if (!snapshot.exists()) return null;

  const entries = Object.entries(snapshot.val());
  if (entries.length === 0) return null;

  const [key, data] = entries[0];
  return { id: data.userId || key, _key: key, ...data };
}

/**
 * 通过用户 ID 查找用户
 * @param {string} userId - 用户 ID
 * @returns {Promise<Object|null>} 用户对象或 null
 */
export async function getUserById(userId) {
  const database = getDB();
  const q = query(
    ref(database, 'users'),
    orderByChild('userId'),
    equalTo(userId),
    limitToFirst(1)
  );

  const snapshot = await get(q);
  if (!snapshot.exists()) return null;

  const entries = Object.entries(snapshot.val());
  if (entries.length === 0) return null;

  const [key, data] = entries[0];
  return { id: data.userId || key, _key: key, ...data };
}

/**
 * 保存用户数据
 * @param {string} userId - 用户 ID
 * @param {Object} data - 要更新的数据
 */
export async function saveUserData(userId, data) {
  const database = getDB();
  let key = userId;

  // 如果是短 ID (usr_xxx)，查找 Firebase key
  if (userId && userId.startsWith('usr_')) {
    const user = await getUserById(userId);
    if (user && user._key) {
      key = user._key;
    } else {
      throw new Error('User not found');
    }
  }

  await update(ref(database, `users/${key}`), data);
}

// ============================================================================
// 记录操作
// ============================================================================

/**
 * 添加扫描记录
 * @param {Object} item - 记录对象
 * @returns {Promise<Object>} 包含新记录 ID
 */
export async function addItem(item) {
  const database = getDB();
  const itemRef = push(ref(database, 'items'));

  await set(itemRef, {
    name: item.name || 'Scanned Item',
    createdAt: Date.now(),
    status: item.mode || 'dispose',
    description: item.description || '',
    photoUrl: item.image_url || '',
    dealtWithMethod: item.disposal_guide || '',
    dealtWithDate: null,
    userId: item.userId || null,
    eco_rate: item.eco_rate || 3,
    recycle_rate: item.recycle_rate || 4,
    overall_score: item.overall_score || 50,
    material: item.material || '',
    grade: item.grade || '',
    brand: item.brand || '',
    category: item.category || '',
    weighted_scores: item.weighted_scores || {},
    schema_id: item.schema_id || '',
    alternative: item.alternative || null,
  });

  return { id: itemRef.key };
}

/**
 * 获取用户的记录列表
 * @param {string} userId - 用户 ID
 * @returns {Promise<Array>} 记录数组
 */
export async function getItems(userId = null) {
  const database = getDB();
  const snapshot = await get(ref(database, 'items'));

  if (!snapshot.exists()) return [];

  const val = snapshot.val();
  let items = Object.keys(val).map(id => ({ id, ...val[id] }));

  // 按时间倒序排序
  items.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));

  // 如果指定了用户 ID，过滤记录
  if (userId) {
    items = items.filter(item => {
      const owner = item.userId || item.userid || item.user || '';
      return !owner || owner === userId;
    });
  }

  return items;
}

/**
 * 删除记录
 * @param {string} itemId - 记录 ID
 */
export async function deleteItem(itemId) {
  const database = getDB();
  await remove(ref(database, `items/${itemId}`));
}

/**
 * 清空所有记录
 */
export async function clearAllItems() {
  const database = getDB();
  const snapshot = await get(ref(database, 'items'));

  if (snapshot.exists()) {
    const promises = Object.keys(snapshot.val()).map(id =>
      remove(ref(database, `items/${id}`))
    );
    await Promise.all(promises);
  }
}
