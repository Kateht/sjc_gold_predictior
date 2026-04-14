import { useEffect, useState, type FormEvent } from 'react';

import { askAssistant, fetchModels, fetchPricePrediction, fetchTrendPrediction } from '@/lib/api';
import { formatMarketPrice, formatNumber } from '@/lib/format';
import { getUserFacingModelLabel } from '@/lib/modelLabels';
import { RichMessage } from '@/components/RichMessage';
import { Sparkline } from '@/components/Sparkline';
import type { ModelRead, PricePredictionResponse, TrendPredictionResponse } from '@/types';

const sourceOptions = [
  { value: 'sjc', label: 'SJC' },
  { value: 'world', label: 'World gold' },
];

const rangeOptions = ['7d', '30d', '90d', '180d', '1y', 'all'];

const resultTabs: Array<{ value: 'chart' | 'timeline' | 'details'; label: string; description: string }> = [
  { value: 'chart', label: 'Chart', description: 'Interactive view' },
  { value: 'timeline', label: 'Timeline', description: 'Step through points' },
  { value: 'details', label: 'Details', description: 'Context and model data' },
];

const assistantSuggestions = [
  'Explain the current SJC spread',
  'Why was the fallback model used?',
  'What should I watch in the next 7 days?',
];

type ResultTab = (typeof resultTabs)[number]['value'];

interface ChatMessage {
  id: number;
  role: 'assistant' | 'user';
  content: string;
}

function pickDefaultModel(models: ModelRead[]): string {
  return models.find((model) => model.is_default)?.code ?? models[0]?.code ?? '';
}

export function PredictPage() {
  const [mode, setMode] = useState<'price' | 'trend'>('price');
  const [resultTab, setResultTab] = useState<ResultTab>('chart');
  const [days, setDays] = useState(7);
  const [source, setSource] = useState('sjc');
  const [range, setRange] = useState('30d');
  const [priceModels, setPriceModels] = useState<ModelRead[]>([]);
  const [trendModels, setTrendModels] = useState<ModelRead[]>([]);
  const [priceModel, setPriceModel] = useState('');
  const [trendModel, setTrendModel] = useState('');
  const [priceResult, setPriceResult] = useState<PricePredictionResponse | null>(null);
  const [trendResult, setTrendResult] = useState<TrendPredictionResponse | null>(null);
  const [assistantQuestion, setAssistantQuestion] = useState('');
  const [assistantMessages, setAssistantMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: 'assistant',
      content: 'Ask me about the forecast, the model choice, or why a fallback was used. I will answer in a chat-style thread.',
    },
  ]);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [priceSelectedIndex, setPriceSelectedIndex] = useState(0);
  const [trendSelectedIndex, setTrendSelectedIndex] = useState(0);
  const [priceHoverIndex, setPriceHoverIndex] = useState<number | null>(null);
  const [trendHoverIndex, setTrendHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let active = true;

    async function loadModels() {
      try {
        const [priceList, trendList] = await Promise.all([fetchModels('price', true), fetchModels('trend', true)]);
        if (!active) {
          return;
        }
        setPriceModels(priceList);
        setTrendModels(trendList);
        setPriceModel((current) => current || pickDefaultModel(priceList));
        setTrendModel((current) => current || pickDefaultModel(trendList));
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load models');
        }
      }
    }

    void loadModels();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (priceResult?.predictions.length) {
      setPriceSelectedIndex(priceResult.predictions.length - 1);
      setPriceHoverIndex(null);
    }
  }, [priceResult]);

  useEffect(() => {
    if (trendResult?.trend_scores.length) {
      setTrendSelectedIndex(trendResult.trend_scores.length - 1);
      setTrendHoverIndex(null);
    }
  }, [trendResult]);

  useEffect(() => {
    setResultTab('chart');
  }, [mode]);

  async function handlePredict(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (mode === 'price') {
        const result = await fetchPricePrediction({ days, model: priceModel || undefined, source, range });
        setPriceResult(result);
        setPriceSelectedIndex(result.predictions.length ? result.predictions.length - 1 : 0);
      } else {
        const result = await fetchTrendPrediction({ days, model: trendModel || undefined, source, range });
        setTrendResult(result);
        setTrendSelectedIndex(result.trend_scores.length ? result.trend_scores.length - 1 : 0);
      }
      setResultTab('chart');
    } catch (predictError) {
      setError(predictError instanceof Error ? predictError.message : 'Prediction failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = assistantQuestion.trim();
    if (!prompt) {
      return;
    }

    setAssistantLoading(true);
    setError('');
    setAssistantMessages((current) => [...current, { id: Date.now(), role: 'user', content: prompt }]);
    setAssistantQuestion('');

    try {
      const answer = await askAssistant(prompt);
      setAssistantMessages((current) => [...current, { id: Date.now() + 1, role: 'assistant', content: answer.answer }]);
    } catch (askError) {
      setError(askError instanceof Error ? askError.message : 'Assistant failed');
      setAssistantMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: 'I could not fetch a fallback answer just now. Please try again after checking the backend connection.',
        },
      ]);
    } finally {
      setAssistantLoading(false);
    }
  }

  function selectPoint(index: number) {
    if (mode === 'price') {
      setPriceSelectedIndex(index);
      return;
    }
    setTrendSelectedIndex(index);
  }

  const activePriceModel = priceModels.find((model) => model.code === priceModel);
  const activeTrendModel = trendModels.find((model) => model.code === trendModel);
  const activeLabels = mode === 'price' ? priceResult?.future_dates ?? [] : trendResult?.future_dates ?? [];
  const activeChartValues = mode === 'price' ? priceResult?.predictions ?? [] : trendResult?.trend_scores ?? [];
  const activeSelectedIndex = mode === 'price' ? priceSelectedIndex : trendSelectedIndex;
  const activePreviewIndex = mode === 'price' ? priceHoverIndex : trendHoverIndex;
  const activePointIndex = activePreviewIndex ?? activeSelectedIndex;
  const activeSelectedValue = activeChartValues[activePointIndex] ?? activeChartValues[activeChartValues.length - 1] ?? 0;
  const activePriceSource = priceResult?.source ?? source;
  const activeSelectedLabel = mode === 'price' ? formatMarketPrice(activeSelectedValue, activePriceSource) : formatNumber(activeSelectedValue);
  const activeSelectedDate = activeLabels[activePointIndex] ?? activeLabels[activeLabels.length - 1] ?? 'N/A';
  const activeSelectedTrend = mode === 'price' ? priceResult?.trend ?? 'trend' : trendResult?.trend_predictions[activePointIndex] ?? 'flat';
  const activeResultModel = mode === 'price' ? priceResult?.selected_model : trendResult?.selected_model;
  const activeUsedFallback = mode === 'price' ? priceResult?.used_fallback : trendResult?.used_fallback;
  const hasActiveResult = activeChartValues.length > 0;
  const chartAccent = mode === 'price' ? '#c9921d' : '#16825d';
  const activePointCount = activeLabels.length;
  const activeModelLabel = getUserFacingModelLabel(activeResultModel);
  const activePointModeLabel = activePreviewIndex !== null ? 'Hovered point' : 'Selected point';

  return (
    <div className="page stack">
      <section className="panel">
        <div className="section-title">
          <div>
            <p className="eyebrow">Prediction studio</p>
            <h3>Run price and trend forecasts with the backend models.</h3>
          </div>
          <div className="tabs">
            <button type="button" className={`tab ${mode === 'price' ? 'is-active' : ''}`} onClick={() => { setMode('price'); setResultTab('chart'); }}>
              Price
            </button>
            <button type="button" className={`tab ${mode === 'trend' ? 'is-active' : ''}`} onClick={() => { setMode('trend'); setResultTab('chart'); }}>
              Trend
            </button>
          </div>
        </div>

        <form className="grid-3" onSubmit={handlePredict}>
          <label className="field">
            <span>Days ahead</span>
            <input className="input" type="number" min={1} max={365} value={days} onChange={(event) => setDays(Number(event.target.value))} />
          </label>

          <label className="field">
            <span>Source</span>
            <select className="select" value={source} onChange={(event) => setSource(event.target.value)}>
              {sourceOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Input range</span>
            <select className="select" value={range} onChange={(event) => setRange(event.target.value)}>
              {rangeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <span className="chat-composer__hint">Counts backward from today when you click Predict.</span>
          </label>

          <label className="field">
            <span>Price model</span>
            <select className="select" value={priceModel} onChange={(event) => setPriceModel(event.target.value)} disabled={mode !== 'price'}>
              {priceModels.map((model) => (
                <option key={model.code} value={model.code}>
                  {getUserFacingModelLabel(model)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Trend model</span>
            <select className="select" value={trendModel} onChange={(event) => setTrendModel(event.target.value)} disabled={mode !== 'trend'}>
              {trendModels.map((model) => (
                <option key={model.code} value={model.code}>
                  {getUserFacingModelLabel(model)}
                </option>
              ))}
            </select>
          </label>

          <div className="field" style={{ alignSelf: 'end' }}>
            <span>&nbsp;</span>
            <button type="submit" className="button button--primary button--full" disabled={loading}>
              {loading ? 'Predicting...' : mode === 'price' ? 'Predict price' : 'Predict trend'}
            </button>
          </div>
        </form>

        {error ? <div className="error-state" style={{ marginTop: '16px' }}>{error}</div> : null}
      </section>

      <section className="grid-2 prediction-stage">
        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Model context</p>
              <h3>{mode === 'price' ? getUserFacingModelLabel(activePriceModel) : getUserFacingModelLabel(activeTrendModel)}</h3>
            </div>
            <span className={`badge ${activeUsedFallback ? 'badge--negative' : 'badge--positive'}`}>{activeUsedFallback ? 'fallback' : 'model-backed'}</span>
          </div>
          <p>{mode === 'price' ? activePriceModel?.description ?? 'Uses the selected price model.' : activeTrendModel?.description ?? 'Uses the selected trend model.'}</p>
          <div className="metric-grid metric-grid--compact">
            <div className="metric-card">
              <span className="metric-card__label">Selected source</span>
              <strong className="metric-card__value">{source.toUpperCase()}</strong>
              <span className="metric-card__meta">Logs with range tag {range}</span>
            </div>
            <div className="metric-card">
              <span className="metric-card__label">Predicted days</span>
              <strong className="metric-card__value">{days}</strong>
              <span className="metric-card__meta">Future horizon</span>
            </div>
          </div>

          <div className="panel panel--compact prediction-chart-card">
            <div className="section-title section-title--tight">
              <div>
                <p className="eyebrow">Interactive result</p>
                <h3>{mode === 'price' ? 'Price path' : 'Trend confidence'}</h3>
              </div>
              <div className="tabs tabs--compact">
                {resultTabs.map((tab) => (
                  <button key={tab.value} type="button" className={`tab ${resultTab === tab.value ? 'is-active' : ''}`} onClick={() => setResultTab(tab.value)}>
                    <span>{tab.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {resultTab === 'chart' ? (
              <div className="prediction-chart">
                <Sparkline
                  values={activeChartValues}
                  labels={activeLabels}
                  height={104}
                  accent={chartAccent}
                  highlightIndex={activePointIndex}
                  onPointSelect={selectPoint}
                  onPointHover={mode === 'price' ? setPriceHoverIndex : setTrendHoverIndex}
                  className="sparkline--hero"
                />

                <div className="forecast-summary">
                  <div>
                    <p className="eyebrow">{activePointModeLabel}</p>
                    <h4>{activeSelectedDate}</h4>
                    <p>{mode === 'price' ? 'Hover or tap a dot or chip to inspect the forecast price.' : 'Hover or tap a dot or chip to inspect the trend confidence.'}</p>
                  </div>
                  <div className="forecast-summary__value">
                    <strong>{activeSelectedLabel}</strong>
                    <span className={`badge ${mode === 'price' ? 'badge--neutral' : activeSelectedTrend === 'up' ? 'badge--positive' : activeSelectedTrend === 'down' ? 'badge--negative' : 'badge--neutral'}`}>
                      {mode === 'price' ? activeSelectedTrend : activeSelectedTrend}
                    </span>
                  </div>
                </div>
              </div>
            ) : null}

            {resultTab === 'timeline' ? (
              <div className="forecast-strip">
                {activeLabels.map((label, index) => {
                  const tone = mode === 'price' ? 'badge--neutral' : activeChartValues[index] >= 0.5 ? 'badge--positive' : 'badge--neutral';
                  const pointValue = mode === 'price' ? formatMarketPrice(activeChartValues[index], activePriceSource) : formatNumber(activeChartValues[index]);

                  return (
                    <button
                      key={`${label}-${index}`}
                      type="button"
                      className={`forecast-pill ${index === activePointIndex ? 'is-active' : ''}`}
                      onClick={() => selectPoint(index)}
                      onMouseEnter={() => {
                        if (mode === 'price') {
                          setPriceHoverIndex(index);
                          return;
                        }
                        setTrendHoverIndex(index);
                      }}
                      onMouseLeave={() => {
                        if (mode === 'price') {
                          setPriceHoverIndex(null);
                          return;
                        }
                        setTrendHoverIndex(null);
                      }}
                      onFocus={() => {
                        if (mode === 'price') {
                          setPriceHoverIndex(index);
                          return;
                        }
                        setTrendHoverIndex(index);
                      }}
                      onBlur={() => {
                        if (mode === 'price') {
                          setPriceHoverIndex(null);
                          return;
                        }
                        setTrendHoverIndex(null);
                      }}
                    >
                      <span>{label}</span>
                      <strong>{pointValue}</strong>
                      <span className={`badge ${tone}`}>{mode === 'price' ? activeSelectedTrend : trendResult?.trend_predictions[index] ?? 'flat'}</span>
                    </button>
                  );
                })}
              </div>
            ) : null}

            {resultTab === 'details' ? (
              <div className="metric-grid metric-grid--compact">
                <div className="metric-card">
                  <span className="metric-card__label">Model</span>
                  <strong className="metric-card__value">{activeModelLabel}</strong>
                  <span className="metric-card__meta">{activeResultModel?.code ?? 'selected model code'}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Forecast point</span>
                  <strong className="metric-card__value">{activeSelectedDate}</strong>
                  <span className="metric-card__meta">{activeSelectedLabel}</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Source</span>
                  <strong className="metric-card__value">{source.toUpperCase()}</strong>
                  <span className="metric-card__meta">Range {range} · {activePointCount} points</span>
                </div>
                <div className="metric-card">
                  <span className="metric-card__label">Fallback</span>
                  <strong className="metric-card__value">{activeUsedFallback ? 'Enabled' : 'Disabled'}</strong>
                  <span className="metric-card__meta">Visible in history and export</span>
                </div>
              </div>
            ) : null}

            {!hasActiveResult ? <div className="empty-state">Run a prediction to inspect the output path.</div> : null}
          </div>
        </article>

        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Prediction result</p>
              <h3>{mode === 'price' ? 'Price forecast' : 'Trend forecast'}</h3>
            </div>
            {activeResultModel ? <span className="badge">{activeResultModel.code}</span> : null}
          </div>

          {mode === 'price' && priceResult ? (
            <div className="timeline-list timeline-list--dense">
              {priceResult.future_dates.map((date, index) => (
                <button
                  key={`${date}-${index}`}
                  type="button"
                  className={`timeline-item timeline-item--button ${index === activePointIndex ? 'is-active' : ''}`}
                  onClick={() => {
                    setPriceSelectedIndex(index);
                    setPriceHoverIndex(null);
                  }}
                  onMouseEnter={() => setPriceHoverIndex(index)}
                  onMouseLeave={() => setPriceHoverIndex(null)}
                  onFocus={() => setPriceHoverIndex(index)}
                  onBlur={() => setPriceHoverIndex(null)}
                >
                  <div className="timeline-item__head">
                    <strong>{date}</strong>
                    <span className="badge">{formatMarketPrice(priceResult.predictions[index], priceResult.source)}</span>
                  </div>
                  <p>{index === 0 ? `First forecast point from ${getUserFacingModelLabel(priceResult.selected_model)}.` : `Forecast point ${index + 1} of ${priceResult.future_dates.length}.`}</p>
                </button>
              ))}
            </div>
          ) : null}

          {mode === 'trend' && trendResult ? (
            <div className="timeline-list timeline-list--dense">
              {trendResult.future_dates.map((date, index) => (
                <button
                  key={`${date}-${index}`}
                  type="button"
                  className={`timeline-item timeline-item--button ${index === activePointIndex ? 'is-active' : ''}`}
                  onClick={() => {
                    setTrendSelectedIndex(index);
                    setTrendHoverIndex(null);
                  }}
                  onMouseEnter={() => setTrendHoverIndex(index)}
                  onMouseLeave={() => setTrendHoverIndex(null)}
                  onFocus={() => setTrendHoverIndex(index)}
                  onBlur={() => setTrendHoverIndex(null)}
                >
                  <div className="timeline-item__head">
                    <strong>{date}</strong>
                    <span className={`badge ${trendResult.trend_predictions[index] === 'up' ? 'badge--positive' : trendResult.trend_predictions[index] === 'down' ? 'badge--negative' : 'badge--neutral'}`}>
                      {trendResult.trend_predictions[index]}
                    </span>
                  </div>
                  <p>Confidence score: {formatNumber(trendResult.trend_scores[index])}</p>
                </button>
              ))}
            </div>
          ) : null}

          {!priceResult && !trendResult ? <div className="empty-state">Run a prediction to inspect the output path.</div> : null}
        </article>
      </section>

      <section className="panel stack chat-panel">
        <div className="section-title">
          <div>
            <p className="eyebrow">AI assistant</p>
            <h3>Chat-style fallback help for gold and the forecast window.</h3>
          </div>
          <span className="badge badge--neutral">Fallback ready</span>
        </div>

        <div className="chat-shell">
          <div className="chat-thread">
            {assistantMessages.map((message) => (
              <div key={message.id} className={`chat-bubble ${message.role === 'assistant' ? 'chat-bubble--assistant' : 'chat-bubble--user'}`}>
                <span className="chat-bubble__label">{message.role === 'assistant' ? 'Assistant' : 'You'}</span>
                <RichMessage content={message.content} />
              </div>
            ))}
            {assistantLoading ? (
              <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                <span className="chat-bubble__label">Assistant</span>
                <div className="chat-typing" aria-label="Assistant is typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            ) : null}
          </div>

          <form className="chat-composer" onSubmit={handleAsk}>
            <div className="chat-suggestions">
              {assistantSuggestions.map((suggestion) => (
                <button key={suggestion} type="button" className="chat-suggestion" onClick={() => setAssistantQuestion(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>

            <label className="field">
              <span>Message</span>
              <textarea className="textarea textarea--chat" value={assistantQuestion} onChange={(event) => setAssistantQuestion(event.target.value)} placeholder="How will SJC move in 7 days?" />
            </label>

            <div className="controls-row controls-row--space-between">
              <span className="chat-composer__hint">Assistant answers are shown in a threaded bubble view.</span>
              <button type="submit" className="button button--primary" disabled={assistantLoading}>
                {assistantLoading ? 'Thinking...' : 'Send message'}
              </button>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}
