// ============================================================================
// 评分计算工具
// ============================================================================

import { SCHEMA_WEIGHTS } from '../constants/schemas';

/**
 * 计算加权总分
 * @param {Object} scores - 各维度分数 {a: 80, b: 75, ...}
 * @param {string} schemaId - 评分模式 ID
 * @returns {number} 加权总分 (0-100)
 */
export function calcWeightedScore(scores, schemaId) {
  const weights = SCHEMA_WEIGHTS[schemaId] || SCHEMA_WEIGHTS.food_new;
  const total = Object.keys(weights).reduce((sum, key) => {
    return sum + (scores[key] || 50) * weights[key];
  }, 0);
  return Math.round(total);
}

/**
 * 根据分数获取等级
 * @param {number} score - 总分
 * @returns {Object} 等级信息
 */
export function getGrade(score) {
  if (score >= 85) {
    return {
      grade: 'Excellent (A)',
      advice: 'Highly Recommended',
      color: '#065f46'
    };
  }
  if (score >= 70) {
    return {
      grade: 'Good (B)',
      advice: 'Acceptable',
      color: '#047857'
    };
  }
  if (score >= 55) {
    return {
      grade: 'Fair (C)',
      advice: 'Consider Alternatives',
      color: '#ca8a04'
    };
  }
  if (score >= 40) {
    return {
      grade: 'Poor (D)',
      advice: 'Avoid if Possible',
      color: '#b45309'
    };
  }
  return {
    grade: 'Very Poor (E)',
    advice: 'Strongly Discouraged',
    color: '#dc2626'
  };
}

/**
 * 生成星级显示
 * @param {number} rating - 评分 (1-5)
 * @returns {string} 星级字符串
 */
export function renderStars(rating) {
  const fullStars = Math.floor(rating);
  const hasHalf = rating % 1 >= 0.5;
  const emptyStars = 5 - fullStars - (hasHalf ? 1 : 0);

  return '★'.repeat(fullStars) +
         (hasHalf ? '☆' : '') +
         '☆'.repeat(emptyStars);
}
