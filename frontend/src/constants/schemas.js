// ============================================================================
// 评分权重配置
// ============================================================================

export const SCHEMA_WEIGHTS = {
  food_new: { a: 0.30, b: 0.25, c: 0.20, d: 0.15, e: 0.10 },
  food_expire: { a: 0.20, b: 0.20, c: 0.25, d: 0.20, e: 0.15 },
  item_new: { a: 0.25, b: 0.35, c: 0.10, d: 0.20, e: 0.10 },
  item_expire: { a: 0.25, b: 0.30, c: 0.10, d: 0.25, e: 0.10 },
};

export const CRITERIA_LABELS = {
  food_new: {
    a: 'Environmental Impact',
    b: 'Sustainability',
    c: 'Biodegradability',
    d: 'Recyclability',
    e: 'Food Preservation'
  },
  food_expire: {
    a: 'Environmental Impact',
    b: 'Sustainability',
    c: 'Biodegradability',
    d: 'Recycling',
    e: 'Safety & Waste Prevention'
  },
  item_new: {
    a: 'Environmental Impact',
    b: 'Sustainability',
    c: 'Biodegradability',
    d: 'Recycling',
    e: 'Social & Innovation'
  },
  item_expire: {
    a: 'Environmental Impact',
    b: 'Sustainability',
    c: 'Biodegradability',
    d: 'Recycling',
    e: 'Reuse Potential'
  },
};

export const ITEM_TYPES = [
  { value: 'food', label: 'Food Items' },
  { value: 'general', label: 'General Items' }
];

export const ITEM_STATES = [
  { value: 'new', label: 'New Purchase' },
  { value: 'expire', label: 'About to Expire' }
];
