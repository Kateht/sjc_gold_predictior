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

type ChartSource = 'sjc' | 'world';
type ChartMode = 'single' | 'compare';

function filterChartByDateRange(chart: PriceChartResponse | null, from: string, to: string): { dates: string[]; prices: number[] } {
  if (!chart || !chart.prices.length) {
    return { dates: [], prices: [] };
  }

  const sortedDates = [from, to].filter(Boolean).sort();
  const startDate = sortedDates[0] ?? '';
  const endDate = sortedDates[1] ?? '';
  if (!startDate && !endDate) {
    return { dates: chart.dates.slice(), prices: chart.prices.slice() };
  }

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

function alignSeriesByDate(
  sjc: { dates: string[]; prices: number[] },
  world: { dates: string[]; prices: number[] },
): { dates: string[]; sjcPrices: number[]; worldPrices: number[] } {
  const sjcMap = new Map(sjc.dates.map((date, index) => [date, sjc.prices[index]] as const));
  const worldMap = new Map(world.dates.map((date, index) => [date, world.prices[index]] as const));
  const dates = [...sjcMap.keys()].filter((date) => worldMap.has(date)).sort();
  return {
    dates,
    sjcPrices: dates.map((date) => sjcMap.get(date) ?? 0),
    worldPrices: dates.map((date) => worldMap.get(date) ?? 0),
  };
}

export function DashboardPage() {
  const { isAuthenticated } = useAuth();
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [chart, setChart] = useState<PriceChartResponse | null>(null);
  const [sjcChart, setSjcChart] = useState<PriceChartResponse | null>(null);
  const [worldChart, setWorldChart] = useState<PriceChartResponse | null>(null);
  const [goldSources, setGoldSources] = useState<GoldSourceRead[]>([]);
  const [chartRange, setChartRange] = useState<DashboardChartRange>('1y');
  const [chartSource, setChartSource] = useState<ChartSource>('sjc');
  const [chartMode, setChartMode] = useState<ChartMode>('single');
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
        if (chartMode === 'compare') {
          const [sjcResponse, worldResponse] = await Promise.all([
            fetchPriceChart(rangeValue, 'sjc'),
            fetchPriceChart(rangeValue, 'world'),
          ]);
          if (!active) {
            return;
          }
          setSjcChart(sjcResponse);
          setWorldChart(worldResponse);
          setChart(null);
        } else {
          const response = await fetchPriceChart(rangeValue, chartSource);
          if (!active) {
            return;
          }
          setChart(response);
          setSjcChart(null);
          setWorldChart(null);
        }
      } catch (loadError) {
        if (!active) {
          return;
        }
        setChart(null);
        setSjcChart(null);
        setWorldChart(null);
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
  }, [chartRange, chartRangeMode, chartSource, chartMode, isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated && chartRangeMode === 'custom') {
      setChartRangeMode('preset');
    }
  }, [chartRangeMode, isAuthenticated]);

  const visibleChart = useMemo(() => {
    if (chartMode === 'compare') {
      const sjcVisible = chartRangeMode === 'custom' && isAuthenticated
        ? filterChartByDateRange(sjcChart, customFrom, customTo)
        : { dates: sjcChart?.dates ?? [], prices: sjcChart?.prices ?? [] };
      const worldVisible = chartRangeMode === 'custom' && isAuthenticated
        ? filterChartByDateRange(worldChart, customFrom, customTo)
        : { dates: worldChart?.dates ?? [], prices: worldChart?.prices ?? [] };

      const aligned = alignSeriesByDate(sjcVisible, worldVisible);
      return {
        mode: 'compare' as const,
        dates: aligned.dates,
        prices: aligned.sjcPrices,
        sjcPrices: aligned.sjcPrices,
        worldPrices: aligned.worldPrices,
      };
    }

    const singleVisible = chartRangeMode === 'custom' && isAuthenticated
      ? filterChartByDateRange(chart, customFrom, customTo)
      : { dates: chart?.dates ?? [], prices: chart?.prices ?? [] };

    return {
      mode: 'single' as const,
      dates: singleVisible.dates,
      prices: singleVisible.prices,
    };
  }, [chart, sjcChart, worldChart, chartMode, chartRangeMode, customFrom, customTo, isAuthenticated]);

  useEffect(() => {
    if (visibleChart.prices.length) {
      setChartSelectedIndex(visibleChart.prices.length - 1);
      setChartHoverIndex(null);
    }
  }, [visibleChart.prices.length, chartRange, chartRangeMode, customFrom, customTo, chartSource, chartMode]);

  const domesticPrice = overview?.domestic_gold.current_price_vnd;
  const worldPrice = overview?.world_gold.current_price_usd;
  const gap = overview?.arbitrage.gap_vnd;
  const gapLabel = gap === undefined || gap === null ? 'N/A' : `${gap >= 0 ? '+' : ''}${gap.toLocaleString('en-US')} VND`;
  const chartPointCount = visibleChart.prices.length;
  const latestChartPrice = chartPointCount ? visibleChart.prices[chartPointCount - 1] : null;
  const latestChartDate = chartPointCount ? visibleChart.dates[chartPointCount - 1] : 'Recent';
  const chartActiveIndex = chartHoverIndex ?? chartSelectedIndex;
  const chartActivePrice = visibleChart.prices[chartActiveIndex] ?? latestChartPrice;
  const chartActiveDate = visibleChart.dates[chartActiveIndex] ?? latestChartDate;
  const chartActiveLabel = chartHoverIndex !== null ? 'Hovered point' : 'Selected point';
  const compareActiveSjc = visibleChart.mode === 'compare' ? visibleChart.sjcPrices?.[chartActiveIndex] ?? null : null;
  const compareActiveWorld = visibleChart.mode === 'compare' ? visibleChart.worldPrices?.[chartActiveIndex] ?? null : null;
  const chartActivePriceLabel = visibleChart.mode === 'compare'
    ? `SJC: ${formatMarketPrice(compareActiveSjc, 'sjc')} | World: ${formatMarketPrice(compareActiveWorld, 'world')}`
    : formatMarketPrice(chartActivePrice, chartSource);
  const chartSourceLabel = chartMode === 'compare' ? 'SJC vs World' : (chartSource === 'world' ? 'World gold' : 'SJC');
  const chartRangeLabel = chartRangeMode === 'custom' && isAuthenticated ? 'Custom range' : chartRange.toUpperCase();
  const chartRangeSubtitle = chartRangeMode === 'custom' && isAuthenticated
    ? `${formatDateOnly(customFrom)} → ${formatDateOnly(customTo)}`
    : 'Preset range';
  const compareSeries = visibleChart.mode === 'compare'
    ? [
        {
          label: 'SJC',
          values: visibleChart.sjcPrices,
          accent: '#c9921d',
        },
        {
          label: 'World',
          values: visibleChart.worldPrices,
          accent: '#2f7dd1',
        },
      ]
    : [];
  const compareSpreadLabel = visibleChart.mode === 'compare' && visibleChart.sjcPrices[chartActiveIndex] !== undefined && visibleChart.worldPrices[chartActiveIndex] !== undefined
    ? `Spread: ${(visibleChart.sjcPrices[chartActiveIndex] - visibleChart.worldPrices[chartActiveIndex]).toLocaleString('en-US')} VND`
    : null;

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
            <div className="chart-tool-group">
              <span className="chart-tool-label">Chart</span>
              <div className="tabs tabs--compact">
                <button type="button" className={`tab ${chartMode === 'single' ? 'is-active' : ''}`} onClick={() => setChartMode('single')}>
                  Single
                </button>
                <button type="button" className={`tab ${chartMode === 'compare' ? 'is-active' : ''}`} onClick={() => setChartMode('compare')}>
                  Compare
                </button>
              </div>
            </div>

            <label className="field">
              <span>Source</span>
              <select
                className="select"
                value={chartSource}
                disabled={chartMode === 'compare'}
                onChange={(event) => setChartSource(event.target.value as ChartSource)}
              >
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
                      if (visibleChart.dates.length) {
                        setCustomFrom((current) => current || visibleChart.dates[0]);
                        setCustomTo((current) => current || visibleChart.dates[visibleChart.dates.length - 1]);
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
          visibleChart.mode === 'compare' ? (
            <div className="stack">
              <Sparkline
                series={compareSeries}
                multiAxisMode="dual"
                labels={visibleChart.dates}
                height={112}
                className="sparkline--hero"
                highlightIndex={chartActiveIndex}
                onPointSelect={setChartSelectedIndex}
                onPointHover={setChartHoverIndex}
              />
              <div className="chip-row chip-row--tight">
                <span className="badge badge--neutral">SJC line</span>
                <span className="badge badge--neutral">World line</span>
                {/* {compareSpreadLabel ? <span className="badge badge--neutral">{compareSpreadLabel}</span> : null} */}
              </div>
            </div>
          ) : (
            <Sparkline
              values={visibleChart.prices}
              labels={visibleChart.dates}
              height={112}
              className="sparkline--hero"
              highlightIndex={chartActiveIndex}
              onPointSelect={setChartSelectedIndex}
              onPointHover={setChartHoverIndex}
            />
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
