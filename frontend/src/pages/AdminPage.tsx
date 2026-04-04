import { useEffect, useState, type FormEvent } from 'react';

import {
  exportAdminHistoryCsv,
  exportDatasetCsv,
  fetchAdminDatasets,
  fetchAdminModels,
  fetchCrawlerRuns,
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

export function AdminPage() {
  const [models, setModels] = useState<ModelRead[]>([]);
  const [datasets, setDatasets] = useState<DatasetSourceRead[]>([]);
  const [runs, setRuns] = useState<CrawlerRunRead[]>([]);
  const [users, setUsers] = useState<UserRead[]>([]);
  const [crawlerForm, setCrawlerForm] = useState(initialCrawlerForm);
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

  async function handleCrawlerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy('crawler');
    setError('');
    try {
      await triggerCrawlerRun({
        task: crawlerForm.task,
        start: crawlerForm.start || undefined,
        end: crawlerForm.end || undefined,
        no_forward_fill: crawlerForm.no_forward_fill,
        bfill_initial: crawlerForm.bfill_initial,
        sleep: crawlerForm.sleep ? Number(crawlerForm.sleep) : undefined,
        quiet: crawlerForm.quiet,
      });
      await reloadAll();
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
      <section className="panel">
        <div className="section-title">
          <div>
            <p className="eyebrow">Admin console</p>
            <h3>Manage models, users, datasets, crawler runs, and exports.</h3>
          </div>
          <button type="button" className="button button--primary" onClick={() => void handleExportAll()} disabled={busy === 'export-all'}>
            {busy === 'export-all' ? 'Exporting...' : 'Export all history'}
          </button>
        </div>
        {error ? <div className="error-state">{error}</div> : null}
        {loading ? <div className="panel panel--compact">Loading admin data...</div> : null}
      </section>

      <section className="grid-2">
        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Models</p>
              <h3>Registry and default selection</h3>
            </div>
          </div>
          <div className="timeline-list">
            {models.map((model) => (
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
          </div>
        </article>

        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Crawler</p>
              <h3>Kick off a backend crawler task</h3>
            </div>
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
        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Datasets</p>
              <h3>Export and inspect registered CSV sources</h3>
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

        <article className="panel stack">
          <div className="section-title">
            <div>
              <p className="eyebrow">Users</p>
              <h3>Role and activation controls</h3>
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
    </div>
  );
}
