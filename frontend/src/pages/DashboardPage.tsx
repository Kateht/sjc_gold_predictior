import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchModels, fetchNewsArticles, fetchOverview, fetchPriceChart } from '@/lib/api';
import { formatDateTime, formatDomesticPrice, formatPercent, formatUsd } from '@/lib/format';
import { getUserFacingModelLabel } from '@/lib/modelLabels';
import type { ModelRead, NewsArticleRead, OverviewResponse, PriceChartResponse } from '@/types';
import { Sparkline } from '@/components/Sparkline';

type DashboardChartRange = '30d' | '90d' | '180d' | '1y';

const CHART_RANGE_OPTIONS: Array<{ value: DashboardChartRange; label: string }> = [
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '180d', label: '180D' },
  { value: '1y', label: '1Y' },
];

const MONTH_STEP_SIZE = 30;
const MAX_ZOOM_STEP = 4;

function formatMonthLabel(dateValue?: string): string {
  if (!dateValue) {
    return 'N/A';
  }
  const parsed = new Date(dateValue);
  if (Number.isNaN(parsed.getTime())) {
    return dateValue;
  }
  return new Intl.DateTimeFormat('vi-VN', { month: 'long', year: 'numeric' }).format(parsed);
}

export function DashboardPage() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [chart, setChart] = useState<PriceChartResponse | null>(null);
  const [chartRange, setChartRange] = useState<DashboardChartRange>('1y');
  const [chartLoading, setChartLoading] = useState(true);
  const [chartError, setChartError] = useState('');
  const [monthShift, setMonthShift] = useState(0);
  const [zoomStep, setZoomStep] = useState(0);
  const [models, setModels] = useState<ModelRead[]>([]);
  const [news, setNews] = useState<NewsArticleRead[]>([]);
  const [error, setError] = useState('');
  const [newsError, setNewsError] = useState('');
  const [loading, setLoading] = useState(true);
  const [chartSelectedIndex, setChartSelectedIndex] = useState(0);
  const [chartHoverIndex, setChartHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      setLoading(true);
      setError('');

      const [overviewResult, modelsResult, newsResult] = await Promise.allSettled([
        fetchOverview(),
        fetchModels(undefined, true),
        fetchNewsArticles(undefined, true, 4),
      ]);

      if (!active) {
        return;
      }

      setOverview(overviewResult.status === 'fulfilled' ? overviewResult.value : null);
      setModels(modelsResult.status === 'fulfilled' ? modelsResult.value : []);
      setNews(newsResult.status === 'fulfilled' ? newsResult.value : []);
      setNewsError(newsResult.status === 'rejected' ? (newsResult.reason instanceof Error ? newsResult.reason.message : 'Failed to load news') : '');

      const firstCriticalError = [overviewResult, modelsResult].find((result) => result.status === 'rejected');
      setError(firstCriticalError && firstCriticalError.status === 'rejected' ? (firstCriticalError.reason instanceof Error ? firstCriticalError.reason.message : 'Failed to load dashboard') : '');
      setLoading(false);
    }

    void loadDashboard();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadChart() {
      setChartLoading(true);
      setChartError('');
      try {
        const response = await fetchPriceChart(chartRange, 'sjc');
        if (!active) {
          return;
        }
        setChart(response);
      } catch (loadError) {
        if (!active) {
          return;
        }
        setChart(null);
        setChartError(loadError instanceof Error ? loadError.message : 'Failed to load chart');
      } finally {
        if (active) {
          setChartLoading(false);
        }
      }
    }

    void loadChart();
    return () => {
      active = false;
    };
  }, [chartRange]);

  const maxMonthShift = useMemo(() => {
    if (chartRange !== '1y' || !chart?.prices.length) {
      return 0;
    }
    return Math.max(0, Math.floor((chart.prices.length - 1) / MONTH_STEP_SIZE));
  }, [chart, chartRange]);

  const normalizedMonthShift = Math.min(monthShift, maxMonthShift);

  useEffect(() => {
    if (monthShift !== normalizedMonthShift) {
      setMonthShift(normalizedMonthShift);
    }
  }, [monthShift, normalizedMonthShift]);

  useEffect(() => {
    if (chartRange !== '1y' && monthShift !== 0) {
      setMonthShift(0);
    }
  }, [chartRange, monthShift]);

  const visibleChart = useMemo(() => {
    if (!chart || !chart.prices.length) {
      return { dates: [] as string[], prices: [] as number[] };
    }

    const totalPoints = chart.prices.length;
    const endOffset = chartRange === '1y' ? normalizedMonthShift * MONTH_STEP_SIZE : 0;
    const endIndex = Math.max(0, totalPoints - 1 - endOffset);
    const baseWindow = chartRange === '1y' ? MONTH_STEP_SIZE : totalPoints;
    const targetWindow = Math.max(7, Math.min(totalPoints, Math.round(baseWindow / (zoomStep + 1))));
    const startIndex = Math.max(0, endIndex - targetWindow + 1);

    return {
      dates: chart.dates.slice(startIndex, endIndex + 1),
      prices: chart.prices.slice(startIndex, endIndex + 1),
    };
  }, [chart, chartRange, normalizedMonthShift, zoomStep]);

  useEffect(() => {
    if (visibleChart.prices.length) {
      setChartSelectedIndex(visibleChart.prices.length - 1);
      setChartHoverIndex(null);
    }
  }, [visibleChart.prices.length, chartRange, normalizedMonthShift, zoomStep]);

  const domesticPrice = overview?.domestic_gold.current_price_vnd;
  const worldPrice = overview?.world_gold.current_price_usd;
  const gap = overview?.arbitrage.gap_vnd;
  const gapLabel = gap === undefined || gap === null ? 'N/A' : `${gap >= 0 ? '+' : ''}${gap.toLocaleString('vi-VN')} VND`;
  const latestChartPrice = visibleChart.prices.length ? visibleChart.prices[visibleChart.prices.length - 1] : null;
  const latestChartDate = visibleChart.dates.length ? visibleChart.dates[visibleChart.dates.length - 1] : 'Recent';
  const chartActiveIndex = chartHoverIndex ?? chartSelectedIndex;
  const chartActivePrice = visibleChart.prices[chartActiveIndex] ?? latestChartPrice;
  const chartActiveDate = visibleChart.dates[chartActiveIndex] ?? latestChartDate;
  const chartActiveLabel = chartHoverIndex !== null ? 'Hovered point' : 'Selected point';
  const canShiftBack = chartRange === '1y' && normalizedMonthShift < maxMonthShift;
  const canShiftForward = chartRange === '1y' && normalizedMonthShift > 0;
  const canZoomIn = zoomStep < MAX_ZOOM_STEP && visibleChart.prices.length > 7;
  const canZoomOut = zoomStep > 0;

  return (
    <div className="page stack">
      <section className="hero panel">
        <div className="hero__content">
          <p className="eyebrow">Market snapshot</p>
          <h3>Domestic and world gold in one clear control room.</h3>
          <p>
            Compare SJC, inspect the current spread, and jump directly into model-based forecasting.
          </p>
          <div className="chip-row">
            <Link className="chip chip--action" to="/predict">
              Open prediction
            </Link>
            <Link className="chip chip--action" to="/news">
              Read latest news
            </Link>
            <Link className="chip chip--action" to="/history">
              View history
            </Link>
          </div>
        </div>
      </section>

      <section className="panel chart-workbench">
        <div className="chart-workbench__head">
          <div>
            <p className="eyebrow">Interactive chart</p>
            <h3>Domestic SJC chart with timeline controls.</h3>
            <p className="section-title__meta">
              {chartActivePrice ? formatDomesticPrice(chartActivePrice) : 'No chart data'} at {chartActiveDate}
            </p>
          </div>
          <span className="badge badge--neutral">{chartActiveLabel}</span>
        </div>

        <div className="chart-workbench__controls">
          <div className="chart-tool-group">
            <span className="chart-tool-label">Range</span>
            <div className="tabs tabs--compact">
              {CHART_RANGE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`tab ${chartRange === option.value ? 'is-active' : ''}`}
                  onClick={() => {
                    setChartRange(option.value);
                    setZoomStep(0);
                    setMonthShift(0);
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="chart-tool-group">
            <span className="chart-tool-label">Month view (1Y)</span>
            <div className="chart-stepper">
              <button type="button" className="button button--ghost" disabled={!canShiftBack} onClick={() => setMonthShift((current) => Math.min(maxMonthShift, current + 1))}>
                Previous month
              </button>
              <span className="chart-stepper__status">{chartRange === '1y' ? formatMonthLabel(latestChartDate) : 'Switch to 1Y to browse by month'}</span>
              <button type="button" className="button button--ghost" disabled={!canShiftForward} onClick={() => setMonthShift((current) => Math.max(0, current - 1))}>
                Next month
              </button>
            </div>
          </div>

          <div className="chart-tool-group">
            <span className="chart-tool-label">Zoom</span>
            <div className="chart-stepper">
              <button type="button" className="button button--ghost" disabled={!canZoomOut} onClick={() => setZoomStep((current) => Math.max(0, current - 1))}>
                Zoom out
              </button>
              <span className="chart-stepper__status">Level {zoomStep + 1}</span>
              <button type="button" className="button button--ghost" disabled={!canZoomIn} onClick={() => setZoomStep((current) => Math.min(MAX_ZOOM_STEP, current + 1))}>
                Zoom in
              </button>
              <button type="button" className="button button--ghost" onClick={() => { setZoomStep(0); setMonthShift(0); }}>
                Reset view
              </button>
            </div>
          </div>
        </div>

        {chartLoading ? <div className="panel panel--compact">Loading chart...</div> : null}
        {chartError ? <div className="empty-state">Chart unavailable: {chartError}</div> : null}

        {!chartLoading && !chartError && visibleChart.prices.length ? (
          <Sparkline
            values={visibleChart.prices}
            labels={visibleChart.dates}
            height={140}
            className="sparkline--hero"
            highlightIndex={chartActiveIndex}
            onPointSelect={setChartSelectedIndex}
            onPointHover={setChartHoverIndex}
          />
        ) : null}

        <p className="hero__chart-hint">Use range, month stepping, and zoom controls to inspect the series in detail.</p>
      </section>

      {loading ? <div className="panel panel--compact">Loading dashboard data...</div> : null}
      {error ? <div className="error-state">{error}</div> : null}

      <section className="metric-grid">
        <article className="metric-card">
          <span className="metric-card__label">Domestic price</span>
          <strong className="metric-card__value">{formatDomesticPrice(domesticPrice)}</strong>
          <span className="metric-card__meta">{overview?.domestic_gold.change_percent !== undefined ? formatPercent(overview?.domestic_gold.change_percent) : 'Stable'}</span>
        </article>
        <article className="metric-card">
          <span className="metric-card__label">World price</span>
          <strong className="metric-card__value">{formatUsd(worldPrice)}</strong>
          <span className="metric-card__meta">{overview?.world_gold.source ?? 'Market feed'}</span>
        </article>
        <article className="metric-card">
          <span className="metric-card__label">Arbitrage gap</span>
          <strong className="metric-card__value">{gapLabel}</strong>
          <span className="metric-card__meta">{overview?.arbitrage.description ?? 'Spread between domestic and converted world price'}</span>
        </article>
        <article className="metric-card">
          <span className="metric-card__label">Last updated</span>
          <strong className="metric-card__value">{formatDateTime(overview?.last_updated)}</strong>
          <span className="metric-card__meta">Model and news cache refreshed from backend.</span>
        </article>
      </section>

      <section className="grid-2">
        <article className="panel">
          <div className="section-title">
            <div>
              <p className="eyebrow">Active models</p>
              <h3>Forecast lineup</h3>
              <p className="section-title__meta">{models.length} active models loaded from the registry.</p>
            </div>
            <Link to="/predict" className="button button--ghost">
              Use model
            </Link>
          </div>
          <div className="stack">
            {models.map((model) => (
              <div key={model.id} className="item-row">
                <div>
                  <strong>{getUserFacingModelLabel(model)}</strong>
                  <p>{model.description ?? model.code}</p>
                </div>
                <div className="chip-row chip-row--tight">
                  <span className="badge">{model.prediction_kind}</span>
                  <span className="badge badge--neutral">{model.provider}</span>
                  {model.is_default ? <span className="badge badge--positive">default</span> : null}
                </div>
              </div>
            ))}
            {!models.length ? <div className="empty-state">No active models loaded.</div> : null}
          </div>
        </article>

        <article className="panel">
          <div className="section-title">
            <div>
              <p className="eyebrow">Featured news</p>
              <h3>Recent context</h3>
            </div>
            <Link to="/news" className="button button--ghost">
              More news
            </Link>
          </div>
          {newsError ? <div className="empty-state">News feed unavailable: {newsError}</div> : null}
          <div className="stack">
            {news.slice(0, 4).map((article) => (
              <article key={article.id} className="item-row item-row--news">
                <div>
                  <strong>{article.title}</strong>
                  <p>{article.summary ?? article.source_name ?? 'Featured analysis'}</p>
                </div>
                <span className="badge badge--neutral">{article.is_featured ? 'featured' : 'news'}</span>
              </article>
            ))}
            {!news.length && !newsError ? <div className="empty-state">No featured articles yet.</div> : null}
          </div>
        </article>
      </section>
    </div>
  );
}
