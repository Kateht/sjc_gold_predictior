import { useEffect, useState } from 'react';

import { exportMyHistoryCsv, fetchPredictionHistory } from '@/lib/api';
import { formatDateTime, formatDomesticPrice, formatNumber } from '@/lib/format';
import type { PredictionHistoryRead } from '@/types';

const PAGE_SIZE = 10;

export function HistoryPage() {
  const [records, setRecords] = useState<PredictionHistoryRead[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;

    async function loadInitial() {
      setLoading(true);
      setError('');
      try {
        const result = await fetchPredictionHistory(PAGE_SIZE, 0);
        if (!active) {
          return;
        }
        setRecords(result);
        setHasMore(result.length === PAGE_SIZE);
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load history');
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadInitial();
    return () => {
      active = false;
    };
  }, []);

  async function loadMore() {
    setLoadingMore(true);
    setError('');
    try {
      const nextOffset = offset + PAGE_SIZE;
      const result = await fetchPredictionHistory(PAGE_SIZE, nextOffset);
      setRecords((current) => [...current, ...result]);
      setOffset(nextOffset);
      setHasMore(result.length === PAGE_SIZE);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load more history');
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    setError('');
    try {
      await exportMyHistoryCsv();
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Failed to export history');
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="page stack">
      <section className="panel">
        <div className="section-title">
          <div>
            <p className="eyebrow">History</p>
            <h3>Track your prediction history and export it as CSV.</h3>
          </div>
          <button type="button" className="button button--primary" onClick={() => void handleExport()} disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        </div>
        {error ? <div className="error-state">{error}</div> : null}
        {loading ? <div className="panel panel--compact">Loading history...</div> : null}
      </section>

      <section className="timeline-list">
        {records.map((record) => {
          const rawPredictions = record.forecast_json['predictions'];
          const predictions = Array.isArray(rawPredictions) ? (rawPredictions as number[]) : [];
          const lastPrediction = predictions.length ? predictions[predictions.length - 1] : null;
          const firstPrediction = predictions.length ? predictions[0] : null;
          const formatForecastValue = record.prediction_kind === 'price' ? formatDomesticPrice : formatNumber;

          return (
            <article key={record.id} className="timeline-item">
              <div className="timeline-item__head">
                <div>
                  <strong>{record.prediction_kind.toUpperCase()}</strong>
                  <p>{formatDateTime(record.created_at)}</p>
                </div>
                <div className="controls-row">
                  <span className="badge">{record.source}</span>
                  <span className={`badge ${record.used_fallback ? 'badge--negative' : 'badge--positive'}`}>{record.used_fallback ? 'fallback' : 'model'}</span>
                </div>
              </div>
              <p>Model: {record.selected_model_key ?? 'N/A'} | Days: {record.days}</p>
              <div className="metric-grid metric-grid--compact">
                <div className="metric-card">
                  <span className="metric-card__label">Trend</span>
                  <strong className="metric-card__value">{record.trend_label ?? 'flat'}</strong>
                  <span className="metric-card__meta">Historical result label</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Forecast range</span>
                  <strong className="metric-card__value">{firstPrediction !== null && lastPrediction !== null ? `${formatForecastValue(firstPrediction)} → ${formatForecastValue(lastPrediction)}` : 'N/A'}</strong>
                  <span className="metric-card__meta">From first to last predicted point</span>
                </div>
              </div>
              <div className="preview-box">{JSON.stringify(record.forecast_json, null, 2)}</div>
            </article>
          );
        })}
      </section>

      {!records.length && !loading ? <div className="empty-state">No prediction history yet.</div> : null}

      {hasMore ? (
        <div className="controls-row">
          <button type="button" className="button button--ghost" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? 'Loading...' : 'Load more'}
          </button>
        </div>
      ) : null}
    </div>
  );
}
