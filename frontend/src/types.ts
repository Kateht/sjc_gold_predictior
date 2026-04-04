export type PredictionKind = 'price' | 'trend';
export type ModelProvider = 'builtin' | 'artifact' | 'ai';

export interface UserRead {
  id: number;
  name: string;
  email: string;
  role: 'user' | 'admin';
  is_active: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserRead;
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  user: UserRead;
}

export interface ModelRead {
  id: number;
  code: string;
  name: string;
  prediction_kind: PredictionKind;
  provider: ModelProvider;
  artifact_path?: string | null;
  description?: string | null;
  config_json?: Record<string, unknown> | null;
  metrics_json?: Record<string, unknown> | null;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface PriceChartResponse {
  dates: string[];
  prices: number[];
}

export interface WorldGoldData {
  status: string;
  message?: string | null;
  current_price_usd?: number | null;
  change_usd?: number | null;
  change_percent?: number | null;
  trend_7d_usd?: number[] | null;
  unit?: string | null;
  source?: string | null;
}

export interface DomesticGoldData {
  status: string;
  message?: string | null;
  current_price_vnd?: number | null;
  change_vnd?: number | null;
  change_percent?: number | null;
  trend_7d_vnd?: number[] | null;
  unit?: string | null;
  source?: string | null;
}

export interface ArbitrageData {
  status?: string | null;
  message?: string | null;
  gap_vnd?: number | null;
  exchange_rate?: number | null;
  converted_world_price_vnd?: number | null;
  description?: string | null;
}

export interface OverviewResponse {
  world_gold: WorldGoldData;
  domestic_gold: DomesticGoldData;
  arbitrage: ArbitrageData;
  last_updated: string;
}

export interface PricePredictionResponse {
  future_dates: string[];
  predictions: number[];
  trend: string;
  selected_model: ModelRead;
  prediction_kind: PredictionKind;
  source: string;
  used_fallback: boolean;
}

export interface TrendPredictionResponse {
  future_dates: string[];
  trend_predictions: string[];
  trend_scores: number[];
  selected_model: ModelRead;
  prediction_kind: PredictionKind;
  source: string;
  used_fallback: boolean;
}

export interface GoldResponse {
  answer: string;
}

export interface NewsCategoryRead {
  id: number;
  slug: string;
  name: string;
  description?: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface NewsArticleRead {
  id: number;
  category_id?: number | null;
  slug: string;
  title: string;
  summary?: string | null;
  content?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  image_url?: string | null;
  published_at?: string | null;
  is_featured: boolean;
  is_active: boolean;
}

export interface PredictionHistoryRead {
  id: number;
  model_id?: number | null;
  prediction_kind: PredictionKind;
  source: string;
  days: number;
  selected_model_key?: string | null;
  trend_label?: string | null;
  used_fallback: boolean;
  forecast_json: Record<string, unknown>;
  created_at: string;
}

export interface GoldSourceRead {
  id: number;
  code: string;
  name: string;
  source_url: string;
  source_type: string;
  description?: string | null;
  region?: string | null;
  sort_order: number;
  is_active: boolean;
}

export interface DatasetSourceRead {
  id: number;
  code: string;
  name: string;
  source_type: string;
  csv_path: string;
  source_url?: string | null;
  file_format: string;
  description?: string | null;
  is_active: boolean;
  is_default: boolean;
  last_synced_at?: string | null;
}

export interface CrawlerRunRead {
  id: number;
  task: string;
  status: string;
  trigger_source: string;
  params_json?: Record<string, unknown> | null;
  exit_code?: number | null;
  output_text?: string | null;
  error_text?: string | null;
  log_path?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  message: string;
}
