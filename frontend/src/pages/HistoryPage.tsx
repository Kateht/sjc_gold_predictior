import { useEffect, useMemo, useState } from 'react';

import { exportMyHistoryCsv, fetchPredictionHistory } from '@/lib/api';
import { formatDateTime, formatMarketPrice, formatNumber } from '@/lib/format';
import type { PredictionHistoryRead } from '@/types';

const PAGE_SIZE = 10;
const kindFilters = [
  { value: 'all', label: 'All records' },
  { value: 'price', label: 'Price only' },
  { value: 'trend', label: 'Trend only' },
] as const;

export function HistoryPage() {
  const [records, setRecords] = useState<PredictionHistoryRead[]>([]);
  const [kindFilter, setKindFilter] = useState<(typeof kindFilters)[number]['value']>('all');
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

  const filteredRecords = useMemo(() => {
    if (kindFilter === 'all') {
      return records;
    }
    return records.filter((record) => record.prediction_kind === kindFilter);
  }, [kindFilter, records]);

  const summary = useMemo(() => {
    const priceCount = records.filter((record) => record.prediction_kind === 'price').length;
    const trendCount = records.filter((record) => record.prediction_kind === 'trend').length;
    const fallbackCount = records.filter((record) => record.used_fallback).length;
    return {
      total: records.length,
      priceCount,
      trendCount,
      fallbackCount,
    };
  }, [records]);

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
      await exportMyHistoryCsv(kindFilter === 'all' ? {} : { prediction_kind: kindFilter });
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
            <h3>Prediction history, summarized for quick review.</h3>
            <p className="section-title__meta">Review past runs by type, model, and source without exposing raw payloads upfront.</p>
          </div>
          <button type="button" className="button button--primary" onClick={() => void handleExport()} disabled={exporting}>
            {exporting ? 'Exporting...' : 'Export CSV'}
          </button>
        </div>

        <div className="metric-grid metric-grid--compact">
          <article className="metric-card">
            <span className="metric-card__label">Loaded</span>
            <strong className="metric-card__value">{summary.total}</strong>
            <span className="metric-card__meta">Records currently in memory</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Price runs</span>
            <strong className="metric-card__value">{summary.priceCount}</strong>
            <span className="metric-card__meta">Price forecasts</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Trend runs</span>
            <strong className="metric-card__value">{summary.trendCount}</strong>
            <span className="metric-card__meta">Direction forecasts</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Fallback</span>
            <strong className="metric-card__value">{summary.fallbackCount}</strong>
            <span className="metric-card__meta">Runs without the primary model</span>
          </article>
        </div>

        <div className="tabs tabs--compact history-filters">
          {kindFilters.map((option) => (
            <button key={option.value} type="button" className={`tab ${kindFilter === option.value ? 'is-active' : ''}`} onClick={() => setKindFilter(option.value)}>
              {option.label}
            </button>
          ))}
        </div>

        {error ? <div className="error-state">{error}</div> : null}
        {loading ? <div className="panel panel--compact">Loading history...</div> : null}
      </section>

      <section className="stack">
        {filteredRecords.map((record) => {
          const rawPredictions = record.forecast_json['predictions'];
          const predictions = Array.isArray(rawPredictions) ? (rawPredictions as number[]) : [];
          const lastPrediction = predictions.length ? predictions[predictions.length - 1] : null;
          const firstPrediction = predictions.length ? predictions[0] : null;
          const formatForecastValue = record.prediction_kind === 'price'
            ? (value: number) => formatMarketPrice(value, record.source)
            : (value: number) => formatNumber(value);

          return (
            <article key={record.id} className="panel stack history-card">
              <div className="history-card__head">
                <div>
                  <p className="eyebrow">{record.prediction_kind === 'price' ? 'Price forecast' : 'Trend forecast'}</p>
                  <h3>{record.selected_model_key ?? 'N/A'} · {record.source.toUpperCase()}</h3>
                  <p className="section-title__meta">{formatDateTime(record.created_at)} · {record.days} days</p>
                </div>
                <div className="controls-row">
                  <span className="badge">{record.source}</span>
                  <span className={`badge ${record.used_fallback ? 'badge--negative' : 'badge--positive'}`}>{record.used_fallback ? 'fallback' : 'model'}</span>
                </div>
              </div>

              <div className="metric-grid metric-grid--compact">
                <div className="metric-card">
                  <span className="metric-card__label">Trend label</span>
                  <strong className="metric-card__value">{record.trend_label ?? 'flat'}</strong>
                  <span className="metric-card__meta">Model output label</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Forecast range</span>
                  <strong className="metric-card__value">{firstPrediction !== null && lastPrediction !== null ? `${formatForecastValue(firstPrediction)} → ${formatForecastValue(lastPrediction)}` : 'N/A'}</strong>
                  <span className="metric-card__meta">From first to last predicted point</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Payload size</span>
                  <strong className="metric-card__value">{predictions.length}</strong>
                  <span className="metric-card__meta">Forecast points stored in the record</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Source tag</span>
                  <strong className="metric-card__value">{record.source.toUpperCase()}</strong>
                  <span className="metric-card__meta">Used for display formatting</span>
                </div>
              </div>

              <details className="history-details">
                <summary>Forecast payload</summary>
                <pre className="preview-box">{JSON.stringify(record.forecast_json, null, 2)}</pre>
              </details>
            </article>
          );
        })}
      </section>

      {!filteredRecords.length && !loading ? <div className="empty-state">No prediction history matches the selected filter.</div> : null}

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
