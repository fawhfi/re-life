// ============================================================================
// 记录列表组件
// ============================================================================

import RecordCard from './RecordCard';
import './RecordList.css';

export default function RecordList({ records, onDelete }) {
  if (records.length === 0) return null;

  return (
    <div className="records-list">
      {records.map((record) => (
        <RecordCard
          key={record.id}
          record={record}
          onDelete={() => onDelete(record.id)}
        />
      ))}
    </div>
  );
}
