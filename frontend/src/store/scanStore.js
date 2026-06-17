// ============================================================================
// 扫描状态管理
// ============================================================================

import { create } from 'zustand';

export const useScanStore = create((set) => ({
  // 状态
  mode: 'dispose', // 'dispose' | 'purchase'
  itemType: 'food', // 'food' | 'general'
  itemState: 'new', // 'new' | 'expire'
  result: null,
  loading: false,
  error: null,
  selectedFile: null,
  previewUrl: null,

  // 设置扫描模式
  setMode: (mode) => set({ mode }),

  // 设置物品类型
  setItemType: (itemType) => set({ itemType }),

  // 设置物品状态
  setItemState: (itemState) => set({ itemState }),

  // 设置选中的文件
  setFile: (file) => {
    if (file) {
      const previewUrl = URL.createObjectURL(file);
      set({ selectedFile: file, previewUrl });
    } else {
      set({ selectedFile: null, previewUrl: null });
    }
  },

  // 设置扫描结果
  setResult: (result) => set({ result, loading: false, error: null }),

  // 设置加载状态
  setLoading: (loading) => set({ loading }),

  // 设置错误
  setError: (error) => set({ error, loading: false }),

  // 重置扫描状态
  reset: () => set({
    result: null,
    loading: false,
    error: null,
    selectedFile: null,
    previewUrl: null,
  }),

  // 清除错误
  clearError: () => set({ error: null }),
}));
