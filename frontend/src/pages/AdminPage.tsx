import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  exportAdminHistoryCsv,
  exportDatasetCsv,
  downloadCrawlerReport,
  fetchAdminDatasets,
  fetchAdminModels,
  fetchCrawlerRuns,
  fetchCrawlerRun,
  fetchUsers,
  setModelDefault,
  setUserRole,
  toggleModelActive,
  toggleUserActive,
  triggerCrawlerRun,
} from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import type { CrawlerRunRead, DatasetSourceRead, ModelRead, UserRead } from '@/types';

const MIN_CRAWLER_SLEEP_SECONDS = 5;

const initialCrawlerForm = {
  task: 'report',
  start: '',
  start_mode: 'selected',
  end: '',
  no_forward_fill: false,
  bfill_initial: false,
  sleep: String(MIN_CRAWLER_SLEEP_SECONDS),
  quiet: true,
};

const crawlerTaskMeta = {
  report: {
    label: '1. Dataset Report',
    description: 'Audit every CSV data file and cache, showing each file\'s date range, continuity, freshness, and status.',
    endDate: true,
  },
  update: {
    label: '2. Update Vietnamese gold',
    description: 'Refresh PNJ and SJC records, then refresh cache and rebuild outputs.',
    endDate: true,
  },
  'backfill-xauusd': {
    label: '3. Update world gold and market dataset',
    description: 'Refresh the XAU/USD cache, then rebuild the market dataset outputs.',
    endDate: true,
  },
  'final-dataset': {
    label: '4. Build ML training dataset',
    description: 'Run tasks 2 and 3, then build final_dataset.csv and its .bak mirror while preserving history.',
    endDate: true,
  },
} as const;

const crawlerWorkflowCards = [
  {
    task: 'report',
    title: '1. Dataset Report',
    description: 'Audit every CSV file and cache with its own date range and status.',
  },
  {
    task: 'final-dataset',
    title: '1. Build ML training dataset',
    description: 'Run the full chain: Vietnamese gold, world gold, market dataset, and final training data.',
  },
  {
    task: 'update',
    title: '2. Update Vietnamese gold',
    description: 'Refresh PNJ and SJC records, then refresh cache and outputs.',
  },
  {
    task: 'backfill-xauusd',
    title: '3. Update world gold and market dataset',
    description: 'Refresh the XAU/USD cache and rebuild the market dataset outputs.',
  },
] as const;

const crawlerStartModeOptions = [
  {
    value: 'selected',
    label: 'Use exact start date',
    description: 'Run exactly from the date you entered.',
  },
  {
    value: 'nearest-data',
    label: 'Start from nearest available date',
    description: 'Move forward to the first available date on or after your selection.',
  },
] as const;

type CrawlerTaskKey = keyof typeof crawlerTaskMeta;
type CrawlerStartModeValue = (typeof crawlerStartModeOptions)[number]['value'];

function normalizeCrawlerSleepValue(value: string): number {
  if (!value.trim()) {
    return MIN_CRAWLER_SLEEP_SECONDS;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return MIN_CRAWLER_SLEEP_SECONDS;
  }

  return Math.max(MIN_CRAWLER_SLEEP_SECONDS, parsed);
}

function readCrawlerDateValue(value: unknown): Date | null {
  if (typeof value !== 'string' || !value.trim()) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function readCrawlerParams(params: Record<string, unknown> | null | undefined): Record<string, unknown> {
  return params && typeof params === 'object' ? params : {};
}

function parseCrawlerProgressDate(outputText: string): Date | null {
  const matches = [...outputText.matchAll(/Crawling\s+(\d{2}\/\d{2}\/\d{4})/g), ...outputText.matchAll(/current\s+(\d{2}\/\d{2}\/\d{4})/g)];
  if (!matches.length) {
    return null;
  }

  const latest = matches[matches.length - 1]?.[1];
  if (!latest) {
    return null;
  }

  const [day, month, year] = latest.split('/').map((part) => Number(part));
  if (!day || !month || !year) {
    return null;
  }

  const parsed = new Date(year, month - 1, day);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function inferCrawlerEndDate(task: string, params: Record<string, unknown>): Date | null {
  const explicitEnd = readCrawlerDateValue(params.end);
  if (explicitEnd) {
    return explicitEnd;
  }

  if (['update', 'update-backfill', 'pipeline', 'report', 'final-uso', 'final-dataset', 'backfill-xauusd'].includes(task)) {
    return new Date();
  }

  return null;
}

function estimateCrawlerProgress(run: CrawlerRunRead): number {
  if (run.status === 'success' || run.status === 'failed') {
    return 100;
  }

  const outputText = run.output_text ?? '';
  const explicitProgressMatches = [...outputText.matchAll(/Progress:\s*(\d{1,3})%/gi)].map((match) => Number(match[1])).filter((value) => Number.isFinite(value));
  let progress = run.status === 'running' ? 10 : 5;

  if (explicitProgressMatches.length) {
    progress = Math.max(progress, Math.max(...explicitProgressMatches));
  }

  const params = readCrawlerParams(run.params_json);
  const startDate = readCrawlerDateValue(params.start);
  const endDate = inferCrawlerEndDate(run.task, params);
  const latestLogDate = parseCrawlerProgressDate(outputText);
  if (startDate && endDate && latestLogDate) {
    const totalDays = Math.max(1, Math.round((endDate.getTime() - startDate.getTime()) / 86_400_000) + 1);
    const processedDays = Math.max(0, Math.min(totalDays, Math.round((latestLogDate.getTime() - startDate.getTime()) / 86_400_000) + 1));
    const rangeProgress = 5 + (processedDays / totalDays) * 85;
    progress = Math.max(progress, Math.round(rangeProgress));
  }

  if (/XAUUSD cache refreshed/i.test(outputText) || /XAUUSD cache refresh complete/i.test(outputText)) {
    progress = Math.max(progress, 80);
  }

  if (/Pipeline outputs:/i.test(outputText)) {
    progress = Math.max(progress, 92);
  }

  if (/final_uso_usd\.csv complete/i.test(outputText) || /Updated final_uso_usd\.csv:/i.test(outputText)) {
    progress = Math.max(progress, 95);
  }

  if (/final_dataset\.csv complete/i.test(outputText) || /Built final_dataset\.csv:/i.test(outputText)) {
    progress = Math.max(progress, 95);
  }

  return Math.min(99, Math.max(5, Math.round(progress)));
}

function getCrawlerStatusMessage(run: CrawlerRunRead): string {
  if (run.status === 'success') {
    return run.task === 'report' ? 'Audit report finished successfully.' : 'Crawler finished successfully.';
  }

  if (run.status === 'failed') {
    return 'Crawler failed. Check the log output below.';
  }

  const outputText = run.output_text ?? '';
  if (outputText.includes('Progress:') || outputText.includes('Crawling ')) {
    return 'Task is running and updating live status...';
  }

  return 'Task is queued and waiting for live updates...';
}

function getCrawlerTaskMeta(task: string) {
  return crawlerTaskMeta[task as CrawlerTaskKey] ?? {
    label: task,
    description: 'This crawler task is not listed in the current UI task catalog.',
    endDate: false,
  };
}

const adminSections = [
  { value: 'overview', label: 'Overview' },
  { value: 'models', label: 'Models' },
  { value: 'crawler', label: 'Crawler' },
  { value: 'datasets', label: 'Datasets' },
  { value: 'users', label: 'Users' },
  { value: 'reports', label: 'Reports' },
] as const;

const modelFilterOptions = [
  { value: 'all', label: 'All models' },
  { value: 'price', label: 'Price' },
  { value: 'trend', label: 'Trend' },
] as const;

const MODEL_PAGE_SIZE = 4;

export function AdminPage() {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [datasets, setDatasets] = useState<DatasetSourceRead[]>([]);
  const [runs, setRuns] = useState<CrawlerRunRead[]>([]);
  const [users, setUsers] = useState<UserRead[]>([]);
  const [crawlerForm, setCrawlerForm] = useState(initialCrawlerForm);
  const [section, setSection] = useState<(typeof adminSections)[number]['value']>('overview');
  const [modelFilter, setModelFilter] = useState<(typeof modelFilterOptions)[number]['value']>('all');
  const [modelPage, setModelPage] = useState(1);
  const [crawlerProgress, setCrawlerProgress] = useState(0);
  const [crawlerStatusMessage, setCrawlerStatusMessage] = useState('');
  const [activeCrawlerRun, setActiveCrawlerRun] = useState<CrawlerRunRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const selectedCrawlerTask = getCrawlerTaskMeta(crawlerForm.task);
  const crawlerTaskUsesEndDate = selectedCrawlerTask.endDate;

  async function reloadAll() {
    setLoading(true);
    setError('');
    try {
      const [modelList, datasetList, runList, userList] = await Promise.all([
        fetchAdminModels(undefined, false),
        fetchAdminDatasets(false),
        fetchCrawlerRuns(20),
        fetchUsers(),
      ]);
      setModels(modelList);
      setDatasets(datasetList);
      setRuns(runList);
      setUsers(userList);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load admin data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reloadAll();
  }, []);

  useEffect(() => {
    setModelPage(1);
  }, [modelFilter]);

  useEffect(() => {
    const target = document.getElementById(section);
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [section]);

  useEffect(() => {
    if (!crawlerTaskUsesEndDate && crawlerForm.end) {
      setCrawlerForm((current) => (current.end ? { ...current, end: '' } : current));
    }
  }, [crawlerTaskUsesEndDate, crawlerForm.end]);

  const filteredModels = useMemo(() => {
    if (modelFilter === 'all') {
      return models;
    }
    return models.filter((model) => model.prediction_kind === modelFilter);
  }, [modelFilter, models]);

  const modelPageCount = Math.max(1, Math.ceil(filteredModels.length / MODEL_PAGE_SIZE));
  const visibleModels = filteredModels.slice((modelPage - 1) * MODEL_PAGE_SIZE, modelPage * MODEL_PAGE_SIZE);

  useEffect(() => {
    if (modelPage > modelPageCount) {
      setModelPage(modelPageCount);
    }
  }, [modelPage, modelPageCount]);

  const latestRun = activeCrawlerRun ?? runs[0] ?? null;
  const latestRunTaskMeta = latestRun ? getCrawlerTaskMeta(latestRun.task) : null;
  const latestRunParams = readCrawlerParams(latestRun?.params_json);
  const crawlerProgressValue = activeCrawlerRun ? estimateCrawlerProgress(activeCrawlerRun) : crawlerProgress;
  const crawlerStatusText = activeCrawlerRun ? getCrawlerStatusMessage(activeCrawlerRun) : crawlerStatusMessage;
  const adminStats = {
    models: models.length,
    datasets: datasets.length,
    users: users.length,
    crawlerRuns: runs.length,
  };

  async function handleModelAction(action: 'default' | 'toggle', model: ModelRead) {
    setBusy(`model-${model.id}`);
    setError('');
    try {
      if (action === 'default') {
        const updated = await setModelDefault(model.code);
        setModels((current) => current.map((item) => (item.prediction_kind === updated.prediction_kind ? { ...item, is_default: item.code === updated.code, is_active: item.code === updated.code ? true : item.is_active } : item)));
      } else {
        const updated = await toggleModelActive(model.code, !model.is_active);
        setModels((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      }
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Failed to update model');
    } finally {
      setBusy('');
    }
  }

  async function handleDatasetExport(dataset: DatasetSourceRead) {
    setBusy(`dataset-${dataset.id}`);
    setError('');
    try {
      await exportDatasetCsv(dataset.code);
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Failed to export dataset');
    } finally {
      setBusy('');
    }
  }

  async function handleCrawlerReportDownload(run: CrawlerRunRead) {
    setBusy(`crawler-report-${run.id}`);
    setError('');
    try {
      await downloadCrawlerReport(run.id);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : 'Failed to download crawler report');
    } finally {
      setBusy('');
    }
  }

  function replaceCrawlerRun(updatedRun: CrawlerRunRead) {
    setRuns((current) => {
      const existingIndex = current.findIndex((run) => run.id === updatedRun.id);
      if (existingIndex === -1) {
        return [updatedRun, ...current];
      }

      const next = [...current];
      next[existingIndex] = updatedRun;
      next.sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
      return next;
    });
  }

  async function monitorCrawlerRun(initialRun: CrawlerRunRead) {
    setActiveCrawlerRun(initialRun);
    setCrawlerProgress(estimateCrawlerProgress(initialRun));
    setCrawlerStatusMessage(getCrawlerStatusMessage(initialRun));

    let latestRun = initialRun;
    let attempts = 0;

    while (!['success', 'failed'].includes(latestRun.status) && attempts < 180) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      latestRun = await fetchCrawlerRun(initialRun.id);
      replaceCrawlerRun(latestRun);
      setActiveCrawlerRun(latestRun);
      attempts += 1;
      setCrawlerProgress(estimateCrawlerProgress(latestRun));
      setCrawlerStatusMessage(getCrawlerStatusMessage(latestRun));
    }

    setActiveCrawlerRun(latestRun);
    setCrawlerProgress(estimateCrawlerProgress(latestRun));
    setCrawlerStatusMessage(
      latestRun.status === 'success'
        ? latestRun.task === 'report'
          ? 'Audit report finished successfully. Download it from the latest run card below.'
          : 'Crawler finished successfully.'
        : 'Crawler failed. Check the log output below.',
    );
    await reloadAll();
  }

  function renderCrawlerReportAction(run: CrawlerRunRead) {
    if (run.task !== 'report' || run.status !== 'success') {
      return null;
    }

    const busyKey = `crawler-report-${run.id}`;
    return (
      <button type="button" className="button button--ghost" onClick={() => void handleCrawlerReportDownload(run)} disabled={busy === busyKey}>
        {busy === busyKey ? 'Preparing...' : 'Download report'}
      </button>
    );
  }

  async function handleCrawlerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy('crawler');
    setError('');
    try {
      const sleepSeconds = normalizeCrawlerSleepValue(crawlerForm.sleep);
      const run = await triggerCrawlerRun({
        task: crawlerForm.task,
        start: crawlerForm.start || undefined,
        start_mode: crawlerForm.start_mode,
        end: crawlerTaskUsesEndDate ? crawlerForm.end || undefined : undefined,
        no_forward_fill: crawlerForm.no_forward_fill,
        bfill_initial: crawlerForm.bfill_initial,
        sleep: sleepSeconds,
        quiet: crawlerForm.quiet,
      });
      replaceCrawlerRun(run);
      await monitorCrawlerRun(run);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to start crawler');
    } finally {
      setBusy('');
    }
  }

  async function handleUserRole(user: UserRead, role: 'user' | 'admin') {
    setBusy(`user-role-${user.id}`);
    setError('');
    try {
      const updated = await setUserRole(user.id, role);
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (roleError) {
      setError(roleError instanceof Error ? roleError.message : 'Failed to update role');
    } finally {
      setBusy('');
    }
  }

  async function handleUserToggle(user: UserRead) {
    setBusy(`user-active-${user.id}`);
    setError('');
    try {
      await toggleUserActive(user.id);
      setUsers((current) => current.map((item) => (item.id === user.id ? { ...item, is_active: !item.is_active } : item)));
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : 'Failed to toggle user status');
    } finally {
      setBusy('');
    }
  }

  async function handleExportAll() {
    setBusy('export-all');
    setError('');
    try {
      await exportAdminHistoryCsv();
    } catch (exportError) {
      setError(exportError instanceof Error ? exportError.message : 'Failed to export prediction history');
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="page stack">
      <section className="panel stack" id="overview">
        <div className="section-title">
          <div>
            <p className="eyebrow">Admin console</p>
            <h3>Manage models, datasets, crawler runs, users, and reports in separate work areas.</h3>
            <p className="section-title__meta">Use the section picker to move between clustered admin tasks instead of scanning one overloaded screen.</p>
          </div>
          <div className="controls-row controls-row--space-between admin-section-picker">
            <label className="field">
              <span>Section</span>
              <select className="select" value={section} onChange={(event) => setSection(event.target.value as (typeof adminSections)[number]['value'])}>
                {adminSections.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="button button--ghost" onClick={() => setSection('reports')}>
              Go to reports
            </button>
          </div>
        </div>

        <div className="metric-grid metric-grid--compact">
          <article className="metric-card">
            <span className="metric-card__label">Models</span>
            <strong className="metric-card__value">{adminStats.models}</strong>
            <span className="metric-card__meta">Registered model entries</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Datasets</span>
            <strong className="metric-card__value">{adminStats.datasets}</strong>
            <span className="metric-card__meta">CSV sources in the catalog</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Users</span>
            <strong className="metric-card__value">{adminStats.users}</strong>
            <span className="metric-card__meta">Accounts with admin and user roles</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Crawler runs</span>
            <strong className="metric-card__value">{adminStats.crawlerRuns}</strong>
            <span className="metric-card__meta">Recent backend jobs tracked here</span>
          </article>
        </div>

        {error ? <div className="error-state">{error}</div> : null}
        {loading ? <div className="panel panel--compact">Loading admin data...</div> : null}
      </section>

      <section className="grid-2">
        <article className="panel stack" id="models">
          <div className="section-title">
            <div>
              <p className="eyebrow">Models</p>
              <h3>Registry, filters, and default selection</h3>
              <p className="section-title__meta">View the registry in pages and filter by model type.</p>
            </div>
            <span className="badge badge--neutral">{filteredModels.length} shown</span>
          </div>

          <div className="tabs tabs--compact">
            {modelFilterOptions.map((option) => (
              <button key={option.value} type="button" className={`tab ${modelFilter === option.value ? 'is-active' : ''}`} onClick={() => setModelFilter(option.value)}>
                {option.label}
              </button>
            ))}
          </div>

          <div className="timeline-list">
            {visibleModels.map((model) => (
              <div key={model.id} className="timeline-item">
                <div className="timeline-item__head">
                  <div>
                    <strong>{model.name}</strong>
                    <p>{model.code}</p>
                  </div>
                  <div className="controls-row">
                    <span className={`badge ${model.is_active ? 'badge--positive' : 'badge--neutral'}`}>{model.is_active ? 'active' : 'inactive'}</span>
                    {model.is_default ? <span className="badge badge--positive">default</span> : null}
                  </div>
                </div>
                <p>{model.description ?? 'No description available.'}</p>
                <div className="controls-row">
                  <button type="button" className="button button--ghost" onClick={() => void handleModelAction('default', model)} disabled={busy === `model-${model.id}`}>
                    Make default
                  </button>
                  <button type="button" className="button button--ghost" onClick={() => void handleModelAction('toggle', model)} disabled={busy === `model-${model.id}`}>
                    {model.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              </div>
            ))}
            {!visibleModels.length ? <div className="empty-state">No models match the selected filter.</div> : null}
          </div>

          <div className="controls-row controls-row--space-between">
            <span className="section-title__meta">
              Page {modelPage} of {modelPageCount}
            </span>
            <div className="controls-row">
              <button type="button" className="button button--ghost" onClick={() => setModelPage((current) => Math.max(1, current - 1))} disabled={modelPage === 1}>
                Previous
              </button>
              <button type="button" className="button button--ghost" onClick={() => setModelPage((current) => Math.min(modelPageCount, current + 1))} disabled={modelPage === modelPageCount}>
                Next
              </button>
            </div>
          </div>
        </article>

        <article className="panel stack" id="crawler">
          <div className="section-title">
            <div>
              <p className="eyebrow">Crawler</p>
              <h3>Run crawler tasks with direct action names and safe delays</h3>
              <p className="section-title__meta">Use the full run when you want Vietnamese gold, world gold, market outputs, and final training data rebuilt together.</p>
            </div>
          </div>

          <div className="crawler-workflow-grid">
            {crawlerWorkflowCards.map((card) => {
              const isActive = crawlerForm.task === card.task;

              return (
                <button key={card.task} type="button" className={`crawler-workflow-card ${isActive ? 'is-active' : ''}`} onClick={() => setCrawlerForm((current) => ({ ...current, task: card.task }))}>
                  <span className="crawler-workflow-card__step">{card.title}</span>
                  <strong>{getCrawlerTaskMeta(card.task).label}</strong>
                  <p>{card.description}</p>
                </button>
              );
            })}
          </div>

          <div className="progress-shell">
            <div className="progress-track" aria-label="Crawler progress">
              <div className="progress-track__bar" style={{ width: `${crawlerProgressValue}%` }} />
            </div>
            <div className="controls-row controls-row--space-between">
              <span className="section-title__meta">{crawlerStatusText || 'Ready to start a crawler run.'}</span>
              <span className="badge badge--neutral">{crawlerProgressValue}%</span>
            </div>
            {latestRun ? (
              <div className="timeline-item timeline-item--button">
                <div className="timeline-item__head">
                  <div>
                    <strong>{latestRunTaskMeta?.label ?? latestRun.task}</strong>
                    <p className="section-title__meta">{latestRunTaskMeta?.description}</p>
                    <p className="section-title__meta">
                      Start: {String(latestRunParams.start ?? 'n/a')} · Mode: {String(latestRunParams.start_mode ?? 'selected')}
                    </p>
                  </div>
                  <span className={`badge ${latestRun.status === 'success' ? 'badge--positive' : latestRun.status === 'failed' ? 'badge--negative' : 'badge--neutral'}`}>{latestRun.status}</span>
                </div>
                <p>{formatDateTime(latestRun.created_at)}</p>
                <div className="controls-row">{renderCrawlerReportAction(latestRun)}</div>
              </div>
            ) : null}
          </div>

          <div className="timeline-item">
            <div className="timeline-item__head">
              <div>
                <strong>Start mode and cache rules</strong>
                <p className="section-title__meta">Use the start mode to either keep the chosen date or snap to the nearest available data date.</p>
              </div>
              <span className="badge badge--neutral">Guide</span>
            </div>
            <p>1. Use <strong>Dataset Report</strong> when you want to audit every CSV file and cache with its own range, continuity, freshness, and status.</p>
            <p>2. Use <strong>Update Vietnamese gold</strong> for PNJ/SJC refreshes; cache and outputs are rebuilt automatically.</p>
            <p>3. Use <strong>Update world gold and market dataset</strong> for the XAU/USD cache and market outputs.</p>
            <p>4. Use <strong>Build ML training dataset</strong> when you want the full chain, including tasks 2 and 3, plus final_dataset.csv.</p>
            <p>5. For crawl-heavy tasks, keep <strong>sleep at 5 seconds or more</strong>. Lower values increase the chance of request blocking.</p>
          </div>

          <form className="stack" onSubmit={handleCrawlerSubmit}>
            <div className="grid-2">
              <label className="field">
                <span>Task</span>
                <select className="select" value={crawlerForm.task} onChange={(event) => setCrawlerForm((current) => ({ ...current, task: event.target.value }))}>
                  <option value="report">1. Dataset Report</option>
                  <option value="final-dataset">2. Build ML training dataset</option>
                  <option value="update">3. Update Vietnamese gold</option>
                  <option value="backfill-xauusd">4. Update world gold and market dataset</option>
                </select>
                <span className="section-title__meta">{selectedCrawlerTask.description}</span>
              </label>
              <label className="field">
                <span>Sleep between requests (seconds)</span>
                <input className="input" type="number" min={MIN_CRAWLER_SLEEP_SECONDS} step="1" value={crawlerForm.sleep} onChange={(event) => setCrawlerForm((current) => ({ ...current, sleep: event.target.value }))} />
                <span className="section-title__meta">Minimum recommended: {MIN_CRAWLER_SLEEP_SECONDS} seconds. Use a higher value if the source starts throttling.</span>
              </label>
              <label className="field">
                <span>Start</span>
                <input className="input" type="date" value={crawlerForm.start} onChange={(event) => setCrawlerForm((current) => ({ ...current, start: event.target.value }))} />
              </label>
              <label className="field">
                <span>Start mode</span>
                <select className="select" value={crawlerForm.start_mode} onChange={(event) => setCrawlerForm((current) => ({ ...current, start_mode: event.target.value as CrawlerStartModeValue }))}>
                  {crawlerStartModeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <span className="section-title__meta">{crawlerStartModeOptions.find((option) => option.value === crawlerForm.start_mode)?.description}</span>
              </label>
              {crawlerTaskUsesEndDate ? (
                <label className="field">
                  <span>End</span>
                  <input className="input" type="date" value={crawlerForm.end} onChange={(event) => setCrawlerForm((current) => ({ ...current, end: event.target.value }))} />
                </label>
              ) : (
                <div className="field">
                  <span>End</span>
                  <span className="section-title__meta">This task uses its own end-date logic, so the field is hidden.</span>
                </div>
              )}
            </div>
            <label className="controls-row" style={{ alignItems: 'center' }}>
              <input type="checkbox" checked={crawlerForm.quiet} onChange={(event) => setCrawlerForm((current) => ({ ...current, quiet: event.target.checked }))} />
              <span>Quiet mode</span>
            </label>
            <label className="controls-row" style={{ alignItems: 'center' }}>
              <input type="checkbox" checked={crawlerForm.no_forward_fill} onChange={(event) => setCrawlerForm((current) => ({ ...current, no_forward_fill: event.target.checked }))} />
              <span>No forward fill</span>
            </label>
            <label className="controls-row" style={{ alignItems: 'center' }}>
              <input type="checkbox" checked={crawlerForm.bfill_initial} onChange={(event) => setCrawlerForm((current) => ({ ...current, bfill_initial: event.target.checked }))} />
              <span>Backward fill initial rows</span>
            </label>
            <button type="submit" className="button button--primary" disabled={busy === 'crawler'}>
              {busy === 'crawler' ? 'Starting...' : 'Start crawler'}
            </button>
          </form>

          <div className="timeline-list">
            {runs.slice(0, 5).map((run) => {
              const taskMeta = getCrawlerTaskMeta(run.task);

              return (
                <div key={run.id} className="timeline-item">
                  <div className="timeline-item__head">
                    <div>
                      <strong>{taskMeta.label}</strong>
                      <p className="section-title__meta">{taskMeta.description}</p>
                    </div>
                    <span className={`badge ${run.status === 'success' ? 'badge--positive' : run.status === 'failed' ? 'badge--negative' : 'badge--neutral'}`}>{run.status}</span>
                  </div>
                  <p>{formatDateTime(run.created_at)}</p>
                  <div className="controls-row">{renderCrawlerReportAction(run)}</div>
                </div>
              );
            })}
          </div>
        </article>
      </section>

      <section className="grid-2">
        <article className="panel stack" id="datasets">
          <div className="section-title">
            <div>
              <p className="eyebrow">Datasets</p>
              <h3>Catalog and export data sources</h3>
              <p className="section-title__meta">Keep the catalog concise with clear labels, sync status, and export actions.</p>
            </div>
          </div>

          <div className="metric-grid metric-grid--compact dataset-summary-grid">
            <article className="metric-card">
              <span className="metric-card__label">History CSV</span>
              <strong className="metric-card__value">{datasets.find((dataset) => dataset.code === 'sjc-history-csv')?.name ?? 'n/a'}</strong>
              <span className="metric-card__meta">Primary chart and prediction dataset</span>
            </article>
            <article className="metric-card">
              <span className="metric-card__label">Crawler export</span>
              <strong className="metric-card__value">{datasets.find((dataset) => dataset.code === 'crawler-export-csv')?.name ?? 'n/a'}</strong>
              <span className="metric-card__meta">Used by the crawler export flow</span>
            </article>
          </div>

          <div className="dataset-catalog">
            {datasets.map((dataset) => (
              <article key={dataset.id} className="dataset-card">
                <div className="dataset-card__head">
                  <div>
                    <strong>{dataset.name}</strong>
                    <p>{dataset.code}</p>
                  </div>
                  <div className="controls-row">
                    {dataset.is_default ? <span className="badge badge--positive">default</span> : null}
                    <span className={`badge ${dataset.is_active ? 'badge--positive' : 'badge--neutral'}`}>{dataset.is_active ? 'active' : 'inactive'}</span>
                  </div>
                </div>
                <p className="dataset-card__description">{dataset.description ?? 'No description available.'}</p>
                <div className="dataset-card__meta-row">
                  <span className="badge badge--neutral">{dataset.source_type}</span>
                  <span className="badge badge--neutral">{dataset.file_format}</span>
                  {dataset.last_synced_at ? <span className="badge badge--neutral">Synced {formatDateTime(dataset.last_synced_at)}</span> : null}
                </div>
                <button type="button" className="button button--ghost" onClick={() => void handleDatasetExport(dataset)} disabled={busy === `dataset-${dataset.id}`}>
                  Download CSV
                </button>
              </article>
            ))}
          </div>
        </article>

        <article className="panel stack" id="users">
          <div className="section-title">
            <div>
              <p className="eyebrow">Users</p>
              <h3>Role and activation controls</h3>
              <p className="section-title__meta">Adjust user role and activation state without leaving the admin workspace.</p>
            </div>
          </div>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <strong>{user.name}</strong>
                      <div>{user.email}</div>
                    </td>
                    <td>
                      <span className={`badge ${user.role === 'admin' ? 'badge--positive' : 'badge--neutral'}`}>{user.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${user.is_active ? 'badge--positive' : 'badge--negative'}`}>{user.is_active ? 'active' : 'inactive'}</span>
                    </td>
                    <td>
                      <div className="controls-row">
                        <button type="button" className="button button--ghost" onClick={() => void handleUserRole(user, user.role === 'admin' ? 'user' : 'admin')} disabled={busy === `user-role-${user.id}`}>
                          Toggle role
                        </button>
                        <button type="button" className="button button--ghost" onClick={() => void handleUserToggle(user)} disabled={busy === `user-active-${user.id}`}>
                          Toggle active
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="panel stack" id="reports">
        <div className="section-title">
          <div>
            <p className="eyebrow">Reports</p>
            <h3>Prediction history exports and audit snapshots</h3>
            <p className="section-title__meta">This is where the export belongs, not in the main admin headline.</p>
          </div>
          <button type="button" className="button button--primary" onClick={() => void handleExportAll()} disabled={busy === 'export-all'}>
            {busy === 'export-all' ? 'Exporting...' : 'Export all history'}
          </button>
        </div>

        <div className="metric-grid metric-grid--compact">
          <article className="metric-card">
            <span className="metric-card__label">Crawler status</span>
            <strong className="metric-card__value">{latestRun?.status ?? 'idle'}</strong>
            <span className="metric-card__meta">Latest tracked crawler run</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Models shown</span>
            <strong className="metric-card__value">{visibleModels.length}</strong>
            <span className="metric-card__meta">Current registry page</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">Dataset exports</span>
            <strong className="metric-card__value">{datasets.length}</strong>
            <span className="metric-card__meta">Sources available to download</span>
          </article>
          <article className="metric-card">
            <span className="metric-card__label">User actions</span>
            <strong className="metric-card__value">{users.length}</strong>
            <span className="metric-card__meta">Role and activation controls</span>
          </article>
        </div>
      </section>
    </div>
  );
}
