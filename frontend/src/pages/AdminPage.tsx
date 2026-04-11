import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  exportAdminHistoryCsv,
  exportDatasetCsv,
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

const initialCrawlerForm = {
  task: 'report',
  start: '',
  end: '',
  no_forward_fill: false,
  bfill_initial: false,
  sleep: '',
  quiet: true,
};

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
    setCrawlerProgress(initialRun.status === 'success' || initialRun.status === 'failed' ? 100 : 18);
    setCrawlerStatusMessage(initialRun.status === 'success' ? 'Crawler completed successfully.' : 'Crawler queued. Waiting for progress updates...');

    let latestRun = initialRun;
    let attempts = 0;

    while (!['success', 'failed'].includes(latestRun.status) && attempts < 24) {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      latestRun = await fetchCrawlerRun(initialRun.id);
      replaceCrawlerRun(latestRun);
      setActiveCrawlerRun(latestRun);
      attempts += 1;
      setCrawlerProgress((current) => Math.min(95, Math.max(current, 18 + attempts * 12)));
      setCrawlerStatusMessage(latestRun.status === 'running' ? 'Crawler is running...' : 'Crawler is queued...');
    }

    setActiveCrawlerRun(latestRun);
    setCrawlerProgress(100);
    setCrawlerStatusMessage(latestRun.status === 'success' ? 'Crawler finished successfully.' : 'Crawler failed. Check the log output below.');
    await reloadAll();
  }

  async function handleCrawlerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy('crawler');
    setError('');
    try {
      const run = await triggerCrawlerRun({
        task: crawlerForm.task,
        start: crawlerForm.start || undefined,
        end: crawlerForm.end || undefined,
        no_forward_fill: crawlerForm.no_forward_fill,
        bfill_initial: crawlerForm.bfill_initial,
        sleep: crawlerForm.sleep ? Number(crawlerForm.sleep) : undefined,
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
              <h3>Kick off a backend crawler task</h3>
              <p className="section-title__meta">The progress bar follows the live crawler run status until completion.</p>
            </div>
          </div>

          <div className="progress-shell">
            <div className="progress-track" aria-label="Crawler progress">
              <div className="progress-track__bar" style={{ width: `${crawlerProgress}%` }} />
            </div>
            <div className="controls-row controls-row--space-between">
              <span className="section-title__meta">{crawlerStatusMessage || 'Ready to start a crawler run.'}</span>
              <span className="badge badge--neutral">{crawlerProgress}%</span>
            </div>
            {latestRun ? (
              <div className="timeline-item timeline-item--button">
                <div className="timeline-item__head">
                  <strong>{latestRun.task}</strong>
                  <span className={`badge ${latestRun.status === 'success' ? 'badge--positive' : latestRun.status === 'failed' ? 'badge--negative' : 'badge--neutral'}`}>{latestRun.status}</span>
                </div>
                <p>{formatDateTime(latestRun.created_at)}</p>
              </div>
            ) : null}
          </div>

          <form className="stack" onSubmit={handleCrawlerSubmit}>
            <div className="grid-2">
              <label className="field">
                <span>Task</span>
                <select className="select" value={crawlerForm.task} onChange={(event) => setCrawlerForm((current) => ({ ...current, task: event.target.value }))}>
                  <option value="report">report</option>
                  <option value="update">update</option>
                  <option value="pipeline">pipeline</option>
                  <option value="update-backfill">update-backfill</option>
                  <option value="backfill-xauusd">backfill-xauusd</option>
                  <option value="final-uso">final-uso</option>
                  <option value="final-dataset">final-dataset</option>
                </select>
              </label>
              <label className="field">
                <span>Sleep</span>
                <input className="input" type="number" min="0" step="0.1" value={crawlerForm.sleep} onChange={(event) => setCrawlerForm((current) => ({ ...current, sleep: event.target.value }))} />
              </label>
              <label className="field">
                <span>Start</span>
                <input className="input" type="date" value={crawlerForm.start} onChange={(event) => setCrawlerForm((current) => ({ ...current, start: event.target.value }))} />
              </label>
              <label className="field">
                <span>End</span>
                <input className="input" type="date" value={crawlerForm.end} onChange={(event) => setCrawlerForm((current) => ({ ...current, end: event.target.value }))} />
              </label>
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
            {runs.slice(0, 5).map((run) => (
              <div key={run.id} className="timeline-item">
                <div className="timeline-item__head">
                  <strong>{run.task}</strong>
                  <span className={`badge ${run.status === 'success' ? 'badge--positive' : run.status === 'failed' ? 'badge--negative' : 'badge--neutral'}`}>{run.status}</span>
                </div>
                <p>{formatDateTime(run.created_at)}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="grid-2">
        <article className="panel stack" id="datasets">
          <div className="section-title">
            <div>
              <p className="eyebrow">Datasets</p>
              <h3>Export and inspect registered CSV sources</h3>
              <p className="section-title__meta">Keep the source catalog in one place and export the CSV backing files from here.</p>
            </div>
          </div>
          <div className="timeline-list">
            {datasets.map((dataset) => (
              <div key={dataset.id} className="timeline-item">
                <div className="timeline-item__head">
                  <div>
                    <strong>{dataset.name}</strong>
                    <p>{dataset.code}</p>
                  </div>
                  <div className="controls-row">
                    {dataset.is_default ? <span className="badge badge--positive">default</span> : null}
                    <span className={`badge ${dataset.is_active ? 'badge--positive' : 'badge--neutral'}`}>{dataset.is_active ? 'active' : 'inactive'}</span>
                  </div>
                </div>
                <p>{dataset.csv_path}</p>
                <button type="button" className="button button--ghost" onClick={() => void handleDatasetExport(dataset)} disabled={busy === `dataset-${dataset.id}`}>
                  Export CSV
                </button>
              </div>
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
