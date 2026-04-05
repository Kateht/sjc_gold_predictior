import { API_BASE_URL } from '@/lib/config';
import { clearSession, loadSession, saveSession, sessionFromTokenPair } from '@/lib/auth';
import type {
  AuthSession,
  CrawlerRunRead,
  DatasetSourceRead,
  GoldResponse,
  GoldSourceRead,
  MessageResponse,
  ModelRead,
  NewsArticleRead,
  NewsCategoryRead,
  OverviewResponse,
  PredictionHistoryRead,
  PriceChartResponse,
  PricePredictionResponse,
  TokenPair,
  TrendPredictionResponse,
  UserRead,
} from '@/types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  params?: Record<string, QueryValue>;
  headers?: HeadersInit;
  retryOnAuthFailure?: boolean;
}

function buildUrl(path: string, params?: Record<string, QueryValue>): string {
  const url = new URL(path.startsWith('http') ? path : `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined || value === '') {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function buildHeaders(init?: HeadersInit, auth = true): Headers {
  const headers = new Headers(init);
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (auth) {
    const session = loadSession();
    if (session?.accessToken) {
      headers.set('Authorization', `Bearer ${session.accessToken}`);
    }
  }
  return headers;
}

async function parseError(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    const json = await response.json().catch(() => null) as { detail?: unknown; message?: unknown } | null;
    const detail = json?.detail ?? json?.message;
    if (typeof detail === 'string') {
      return detail;
    }
  }
  const text = await response.text().catch(() => '');
  return text || response.statusText || 'Request failed';
}

async function refreshStoredSession(): Promise<AuthSession | null> {
  const session = loadSession();
  if (!session?.refreshToken) {
    return null;
  }

  const response = await fetch(buildUrl('/auth/refresh'), {
    method: 'POST',
    headers: buildHeaders(undefined, false),
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });

  if (!response.ok) {
    clearSession();
    return null;
  }

  const payload = (await response.json()) as TokenPair;
  const nextSession = sessionFromTokenPair(payload);
  saveSession(nextSession);
  return nextSession;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { auth = true, retryOnAuthFailure = true } = options;
  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? 'GET',
    headers: buildHeaders(options.headers, auth),
    body: options.body === undefined || options.body === null ? undefined : JSON.stringify(options.body),
  });

  if (response.status === 401 && auth && retryOnAuthFailure) {
    const refreshed = await refreshStoredSession();
    if (refreshed) {
      return request<T>(path, { ...options, retryOnAuthFailure: false });
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    return (await response.json()) as T;
  }
  return (await response.text()) as T;
}

export async function downloadCsv(path: string, filename: string, params?: Record<string, QueryValue>): Promise<void> {
  const response = await fetch(buildUrl(path, params), {
    headers: buildHeaders(undefined, true),
  });

  if (response.status === 401) {
    const refreshed = await refreshStoredSession();
    if (refreshed) {
      return downloadCsv(path, filename, params);
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export function getCurrentSession(): AuthSession | null {
  return loadSession();
}

export function saveAuthSession(session: AuthSession): void {
  saveSession(session);
}

export function clearAuthSession(): void {
  clearSession();
}

export async function loginUser(email: string, password: string): Promise<AuthSession> {
  const payload = await request<TokenPair>('/auth/login', {
    method: 'POST',
    auth: false,
    body: { email, password },
  });
  return sessionFromTokenPair(payload);
}

export async function registerUser(name: string, email: string, password: string): Promise<AuthSession> {
  const payload = await request<TokenPair>('/auth/register', {
    method: 'POST',
    auth: false,
    body: { name, email, password },
  });
  return sessionFromTokenPair(payload);
}

export async function logoutUser(refreshToken: string): Promise<void> {
  await request<MessageResponse>('/auth/logout', {
    method: 'POST',
    body: { refresh_token: refreshToken },
  });
}

export async function fetchCurrentUser(): Promise<UserRead> {
  return request<UserRead>('/auth/me');
}

export async function fetchOverview(): Promise<OverviewResponse> {
  return request<OverviewResponse>('/overview', { auth: false });
}

export async function fetchPriceChart(range = '30d', source = 'sjc'): Promise<PriceChartResponse> {
  return request<PriceChartResponse>('/price-chart', {
    auth: false,
    params: { range, source },
  });
}

export async function fetchModels(predictionKind?: string, activeOnly = true): Promise<ModelRead[]> {
  return request<ModelRead[]>('/models', {
    auth: false,
    params: { prediction_kind: predictionKind, active_only: activeOnly },
  });
}

export async function fetchNewsCategories(): Promise<NewsCategoryRead[]> {
  return request<NewsCategoryRead[]>('/news/categories', { auth: false });
}

export async function fetchNewsArticles(category?: string, featured = false, limit = 20): Promise<NewsArticleRead[]> {
  return request<NewsArticleRead[]>('/news/articles', {
    auth: false,
    params: { category, featured, limit },
  });
}

export async function fetchNewsArticleBySlug(slug: string): Promise<NewsArticleRead> {
  return request<NewsArticleRead>(`/news/articles/${slug}`, { auth: false });
}

export async function fetchPricePrediction(params: { days: number; model?: string; source?: string; range?: string }): Promise<PricePredictionResponse> {
  return request<PricePredictionResponse>('/predict', {
    params: {
      days: params.days,
      model: params.model,
      source: params.source ?? 'sjc',
      range: params.range,
    },
  });
}

export async function fetchTrendPrediction(params: { days: number; model?: string; source?: string; range?: string }): Promise<TrendPredictionResponse> {
  return request<TrendPredictionResponse>('/predict/trend', {
    params: {
      days: params.days,
      model: params.model,
      source: params.source ?? 'sjc',
      range: params.range,
    },
  });
}

export async function askAssistant(question: string): Promise<GoldResponse> {
  return request<GoldResponse>('/assistant/queries', {
    method: 'POST',
    auth: false,
    body: { question },
  });
}

export async function fetchPredictionHistory(limit = 20, offset = 0): Promise<PredictionHistoryRead[]> {
  return request<PredictionHistoryRead[]>('/history/predictions', {
    params: { limit, offset },
  });
}

export async function exportMyHistoryCsv(params: Record<string, QueryValue> = {}): Promise<void> {
  return downloadCsv('/history/predictions/export', 'my-prediction-history.csv', params);
}

export async function fetchGoldSources(): Promise<GoldSourceRead[]> {
  return request<GoldSourceRead[]>('/sources/gold', { auth: false });
}

export async function fetchAdminModels(predictionKind?: string, activeOnly = false): Promise<ModelRead[]> {
  return request<ModelRead[]>('/admin/models', {
    params: { prediction_kind: predictionKind, active_only: activeOnly },
  });
}

export async function fetchAdminDatasets(activeOnly = false): Promise<DatasetSourceRead[]> {
  return request<DatasetSourceRead[]>('/admin/datasets', {
    params: { active_only: activeOnly },
  });
}

export async function fetchCrawlerRuns(limit = 20): Promise<CrawlerRunRead[]> {
  return request<CrawlerRunRead[]>('/admin/crawler/runs', {
    params: { limit },
  });
}

export async function triggerCrawlerRun(payload: Record<string, unknown>): Promise<CrawlerRunRead> {
  return request<CrawlerRunRead>('/admin/crawler/runs', {
    method: 'POST',
    body: payload,
  });
}

export async function exportAdminHistoryCsv(params: Record<string, QueryValue> = {}): Promise<void> {
  return downloadCsv('/admin/predictions/export', 'all-prediction-history.csv', params);
}

export async function fetchUsers(): Promise<UserRead[]> {
  return request<UserRead[]>('/admin/users');
}

export async function setUserRole(userId: number, role: 'user' | 'admin'): Promise<UserRead> {
  return request<UserRead>(`/admin/users/${userId}/role`, {
    method: 'PATCH',
    body: { role },
  });
}

export async function toggleUserActive(userId: number): Promise<MessageResponse> {
  return request<MessageResponse>(`/admin/users/${userId}/toggle-active`, {
    method: 'POST',
    body: {},
  });
}

export async function setModelDefault(identifier: string): Promise<ModelRead> {
  return request<ModelRead>(`/admin/models/${identifier}/default`, {
    method: 'POST',
  });
}

export async function toggleModelActive(identifier: string, active: boolean): Promise<ModelRead> {
  return request<ModelRead>(`/admin/models/${identifier}/${active ? 'activate' : 'deactivate'}`, {
    method: 'POST',
  });
}

export async function exportDatasetCsv(identifier: string): Promise<void> {
  return downloadCsv(`/admin/datasets/${identifier}/export`, `${identifier}.csv`);
}
