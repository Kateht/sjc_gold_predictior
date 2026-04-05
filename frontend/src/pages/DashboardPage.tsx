import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchGoldSources, fetchModels, fetchNewsArticles, fetchOverview, fetchPriceChart } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { formatDateOnly, formatDateTime, formatDomesticPrice, formatMarketPrice, formatPercent, formatUsd } from '@/lib/format';
import { getUserFacingModelLabel } from '@/lib/modelLabels';
import type { GoldSourceRead, ModelRead, NewsArticleRead, OverviewResponse, PriceChartResponse } from '@/types';
import { Sparkline } from '@/components/Sparkline';

type DashboardChartRange = '30d' | '90d' | '180d' | '1y';

const CHART_RANGE_OPTIONS: Array<{ value: DashboardChartRange; label: string }> = [
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '180d', label: '180D' },
  { value: '1y', label: '1Y' },
];

export function DashboardPage() {
  const { isAuthenticated } = useAuth();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [chart, setChart] = useState<PriceChartResponse | null>(null);
  const [goldSources, setGoldSources] = useState<GoldSourceRead[]>([]);
  const [chartRange, setChartRange] = useState<DashboardChartRange>('1y');
  const [chartSource, setChartSource] = useState<'sjc' | 'world'>('sjc');
  const [chartView, setChartView] = useState<'chart' | 'numbers'>('chart');
  const [chartRangeMode, setChartRangeMode] = useState<'preset' | 'custom'>('preset');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [chartLoading, setChartLoading] = useState(true);
  const [chartError, setChartError] = useState('');
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

      const [overviewResult, modelsResult, newsResult, sourcesResult] = await Promise.allSettled([
        fetchOverview(),
        fetchModels(undefined, true),
        fetchNewsArticles(undefined, true, 6),
        fetchGoldSources(),
      ]);

      if (!active) {
        return;
      }

      setOverview(overviewResult.status === 'fulfilled' ? overviewResult.value : null);
      setModels(modelsResult.status === 'fulfilled' ? modelsResult.value : []);
      setNews(newsResult.status === 'fulfilled' ? newsResult.value : []);
      setGoldSources(sourcesResult.status === 'fulfilled' ? sourcesResult.value : []);
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
        const rangeValue = chartRangeMode === 'custom' && isAuthenticated ? 'all' : chartRange;
        const response = await fetchPriceChart(rangeValue, chartSource);
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
  }, [chartRange, chartRangeMode, chartSource, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated && chartRangeMode === 'custom') {
      setChartRangeMode('preset');
    }
  }, [chartRangeMode, isAuthenticated]);

  const visibleChart = useMemo(() => {
    if (!chart || !chart.prices.length) {
      return { dates: [] as string[], prices: [] as number[] };
    }

    if (chartRangeMode === 'custom' && isAuthenticated) {
      const sortedDates = [customFrom, customTo].filter(Boolean).sort();
      const startDate = sortedDates[0] ?? '';
      const endDate = sortedDates[1] ?? '';
      const filtered = chart.dates
        .map((date, index) => ({ date, price: chart.prices[index] }))
        .filter((item) => {
          const afterStart = !startDate || item.date >= startDate;
          const beforeEnd = !endDate || item.date <= endDate;
          return afterStart && beforeEnd;
        });

      return {
        dates: filtered.map((item) => item.date),
        prices: filtered.map((item) => item.price),
      };
    }

    return {
      dates: chart.dates,
      prices: chart.prices,
    };
  }, [chart, chartRangeMode, customFrom, customTo, isAuthenticated]);

  useEffect(() => {
    if (visibleChart.prices.length) {
      setChartSelectedIndex(visibleChart.prices.length - 1);
      setChartHoverIndex(null);
    }
  }, [visibleChart.prices.length, chartRange, chartRangeMode, customFrom, customTo, chartSource]);

  const domesticPrice = overview?.domestic_gold.current_price_vnd;
  const worldPrice = overview?.world_gold.current_price_usd;
  const gap = overview?.arbitrage.gap_vnd;
  const gapLabel = gap === undefined || gap === null ? 'N/A' : `${gap >= 0 ? '+' : ''}${gap.toLocaleString('vi-VN')} VND`;
  const chartPointCount = visibleChart.prices.length;
  const latestChartPrice = chartPointCount ? visibleChart.prices[chartPointCount - 1] : null;
  const latestChartDate = chartPointCount ? visibleChart.dates[chartPointCount - 1] : 'Recent';
  const chartActiveIndex = chartHoverIndex ?? chartSelectedIndex;
  const chartActivePrice = visibleChart.prices[chartActiveIndex] ?? latestChartPrice;
  const chartActiveDate = visibleChart.dates[chartActiveIndex] ?? latestChartDate;
  const chartActiveLabel = chartHoverIndex !== null ? 'Hovered point' : 'Selected point';
  const chartActivePriceLabel = formatMarketPrice(chartActivePrice, chartSource);
  const chartSourceLabel = chartSource === 'world' ? 'World gold' : 'SJC';
  const chartRangeLabel = chartRangeMode === 'custom' && isAuthenticated ? 'Custom range' : chartRange.toUpperCase();
  const chartRangeSubtitle = chartRangeMode === 'custom' && isAuthenticated
    ? `${formatDateOnly(customFrom)} → ${formatDateOnly(customTo)}`
    : 'Preset range';

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
            <h3>{chartSourceLabel} chart with timeline controls.</h3>
            <p className="section-title__meta">
              {chartActivePriceLabel} at {chartActiveDate}
            </p>
          </div>
          <div className="controls-row">
            <span className="badge badge--neutral">{chartActiveLabel}</span>
            <span className="badge badge--neutral">{chartRangeLabel}</span>
          </div>
        </div>

        <div className="chart-workbench__controls">
          <div className="chart-tool-group">
            <span className="chart-tool-label">View mode</span>
            <div className="tabs tabs--compact">
              <button type="button" className={`tab ${chartView === 'chart' ? 'is-active' : ''}`} onClick={() => setChartView('chart')}>
                Graph
              </button>
              <button type="button" className={`tab ${chartView === 'numbers' ? 'is-active' : ''}`} onClick={() => setChartView('numbers')}>
                Numbers
              </button>
            </div>
          </div>

          <div className="grid-2">
            <label className="field">
              <span>Source</span>
              <select className="select" value={chartSource} onChange={(event) => setChartSource(event.target.value as 'sjc' | 'world')}>
                <option value="sjc">SJC</option>
                <option value="world">World gold</option>
              </select>
            </label>

            <div className="chart-tool-group">
              <span className="chart-tool-label">Range</span>
              {isAuthenticated ? (
                <div className="tabs tabs--compact">
                  <button type="button" className={`tab ${chartRangeMode === 'preset' ? 'is-active' : ''}`} onClick={() => setChartRangeMode('preset')}>
                    Preset
                  </button>
                  <button
                    type="button"
                    className={`tab ${chartRangeMode === 'custom' ? 'is-active' : ''}`}
                    onClick={() => {
                      setChartRangeMode('custom');
                      if (chart?.dates.length) {
                        setCustomFrom((current) => current || chart.dates[0]);
                        setCustomTo((current) => current || chart.dates[chart.dates.length - 1]);
                      }
                    }}
                  >
                    Custom
                  </button>
                </div>
              ) : null}

              {chartRangeMode === 'preset' || !isAuthenticated ? (
                <div className="tabs tabs--compact chart-range-tabs">
                  {CHART_RANGE_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={`tab ${chartRange === option.value ? 'is-active' : ''}`}
                      onClick={() => setChartRange(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="grid-2 chart-range-grid">
                  <label className="field">
                    <span>From</span>
                    <input className="input" type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} />
                  </label>
                  <label className="field">
                    <span>To</span>
                    <input className="input" type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} />
                  </label>
                </div>
              )}
            </div>
          </div>

          <p className="hero__chart-hint">
            {isAuthenticated
              ? 'Signed-in users can slice the full historical feed by date. Guests are limited to the latest one year of history.'
              : 'Guest access is limited to the latest one year of history.'}
            {chartRangeMode === 'custom' && isAuthenticated ? ` Active window: ${chartRangeSubtitle}.` : ''}
          </p>

          <div className="chip-row source-chip-row">
            {goldSources.slice(0, 4).map((sourceItem) => (
              <a key={sourceItem.id} className="chip chip--action" href={sourceItem.source_url} target="_blank" rel="noreferrer">
                <span>{sourceItem.name}</span>
              </a>
            ))}
          </div>
        </div>

        {chartLoading ? <div className="panel panel--compact">Loading chart...</div> : null}
        {chartError ? <div className="empty-state">Chart unavailable: {chartError}</div> : null}

        {!chartLoading && !chartError && visibleChart.prices.length ? (
          chartView === 'chart' ? (
            <div className="prediction-chart">
              <Sparkline
                values={visibleChart.prices}
                labels={visibleChart.dates}
                height={104}
                className="sparkline--hero"
                highlightIndex={chartActiveIndex}
                onPointSelect={setChartSelectedIndex}
                onPointHover={setChartHoverIndex}
              />

              <div className="forecast-summary">
                <div>
                  <p className="eyebrow">Selected point</p>
                  <h4>{chartActiveDate}</h4>
                  <p>Use the source picker and range controls to inspect the series in detail.</p>
                </div>
                <div className="forecast-summary__value">
                  <strong>{chartActivePriceLabel}</strong>
                  <span className="badge badge--neutral">{chartSourceLabel}</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="chart-number-grid">
              {visibleChart.dates.map((date, index) => (
                <div key={`${date}-${index}`} className="chart-number-card">
                  <span className="chart-number-card__date">{date}</span>
                  <strong>{formatMarketPrice(visibleChart.prices[index], chartSource)}</strong>
                </div>
              ))}
            </div>
          )
        ) : null}

        {!chartLoading && !chartError && !visibleChart.prices.length ? <div className="empty-state">No data found for the selected range.</div> : null}

        <p className="hero__chart-hint">
          {chartView === 'chart'
            ? 'Use the chart dots or switch to numbers mode to inspect the same filtered series in a compact list.'
            : 'Numbers mode mirrors the same filtered series without the chart.'}
        </p>
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
