// ============================================================================
// 记录相关 Hook
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';
import { addItem, getItems, deleteItem, clearAllItems } from '../utils/firebase';

/**
 * 记录 Hook
 * @returns {Object} 记录相关状态和方法
 */
export function useRecords() {
  const { user } = useAuthStore();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // 加载记录
  const loadRecords = useCallback(async () => {
    if (!user) return;

    setLoading(true);
    setError(null);

    try {
      const items = await getItems(user.id);
      setRecords(items);
    } catch (err) {
      console.error('[Records] Load failed:', err);
      setError(err.message || 'Failed to load records');
    } finally {
      setLoading(false);
    }
  }, [user]);

  // 添加记录
  const addRecord = useCallback(async (item) => {
    if (!user) {
      throw new Error('Not authenticated');
    }

    try {
      const result = await addItem({
        ...item,
        userId: user.id,
      });

      // 重新加载记录
      await loadRecords();

      return result;
    } catch (err) {
      console.error('[Records] Add failed:', err);
      throw err;
    }
  }, [user, loadRecords]);

  // 删除记录
  const removeRecord = useCallback(async (itemId) => {
    try {
      await deleteItem(itemId);
      // 更新本地状态
      setRecords(prev => prev.filter(item => item.id !== itemId));
    } catch (err) {
      console.error('[Records] Delete failed:', err);
      throw err;
    }
  }, []);

  // 清空所有记录
  const clearRecords = useCallback(async () => {
    try {
      await clearAllItems();
      setRecords([]);
    } catch (err) {
      console.error('[Records] Clear failed:', err);
      throw err;
    }
  }, []);

  // 计算统计数据
  const stats = {
    count: records.length,
    avgEco: records.length > 0
      ? (records.reduce((sum, r) => sum + (r.eco_rate || 0), 0) / records.length).toFixed(1)
      : '0.0',
    avgRecycle: records.length > 0
      ? (records.reduce((sum, r) => sum + (r.recycle_rate || 0), 0) / records.length).toFixed(1)
      : '0.0',
  };

  // 初始加载
  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  return {
    records,
    loading,
    error,
    stats,
    loadRecords,
    addRecord,
    removeRecord,
    clearRecords,
  };
}
