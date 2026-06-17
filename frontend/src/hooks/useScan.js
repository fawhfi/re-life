// ============================================================================
// 扫描相关 Hook
// ============================================================================

import { useCallback } from 'react';
import { useScanStore } from '../store/scanStore';
import { useSettingsStore } from '../store/settingsStore';
import { scanImage } from '../api/scan';
import { validateImageFile } from '../utils/validation';

/**
 * 扫描 Hook
 * @returns {Object} 扫描相关状态和方法
 */
export function useScan() {
  const {
    mode,
    itemType,
    itemState,
    result,
    loading,
    error,
    selectedFile,
    previewUrl,
    setMode,
    setItemType,
    setItemState,
    setFile,
    setResult,
    setLoading,
    setError,
    reset,
    clearError,
  } = useScanStore();

  const { addPoints } = useSettingsStore();

  // 扫描图像
  const scan = useCallback(async (file) => {
    // 验证文件
    const validation = validateImageFile(file);
    if (!validation.valid) {
      setError(validation.errors.join(', '));
      return;
    }

    setLoading(true);
    clearError();

    try {
      const result = await scanImage(file, {
        mode,
        itemType,
        itemState,
      });

      setResult(result);

      // 根据评分奖励积分
      const points = Math.max(10, Math.floor(result.overall_score / 2));
      addPoints(points);

      return result;
    } catch (err) {
      const errorMessage = err.message || 'Scan failed. Please try again.';
      setError(errorMessage);
      throw err;
    }
  }, [mode, itemType, itemState, setLoading, setResult, setError, clearError, addPoints]);

  // 选择文件并扫描
  const selectAndScan = useCallback(async (file) => {
    setFile(file);
    return scan(file);
  }, [setFile, scan]);

  return {
    mode,
    itemType,
    itemState,
    result,
    loading,
    error,
    selectedFile,
    previewUrl,
    setMode,
    setItemType,
    setItemState,
    setFile,
    scan,
    selectAndScan,
    reset,
    clearError,
  };
}
