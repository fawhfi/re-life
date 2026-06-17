// ============================================================================
// 记录页面
// ============================================================================

import { useRecords } from '../hooks/useRecords';
import RecordList from '../components/records/RecordList';
import RecordStats from '../components/records/RecordStats';
import Button from '../components/common/Button';
import Spinner from '../components/common/Spinner';
import './RecordsPage.css';

export default function RecordsPage() {
  const {
    records,
    loading,
    stats,
    removeRecord,
    clearRecords,
  } = useRecords();

  const handleClearAll = async () => {
    if (window.confirm('确定要清空所有记录吗？此操作无法撤销。')) {
      try {
        await clearRecords();
      } catch (err) {
        alert('清空失败：' + err.message);
      }
    }
  };

  if (loading) {
    return <Spinner message="Loading records..." />;
  }

  return (
    <section className="tab active">
      <RecordStats stats={stats} />

      {records.length > 0 && (
        <Button
          variant="danger"
          fullWidth
          onClick={handleClearAll}
        >
          Clear All
        </Button>
      )}

      <RecordList
        records={records}
        onDelete={removeRecord}
      />

      {records.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📝</div>
          <div className="empty-state-text">No records yet</div>
          <div className="empty-state-hint">Start by scanning an item</div>
        </div>
      )}
    </section>
  );
}
