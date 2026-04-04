import type { ModelRead } from '@/types';

const friendlyLabels: Record<string, string> = {
  'linear-price-v1': 'Linear price forecast',
  'momentum-price-v1': 'Momentum price forecast',
  'mean-reversion-price-v1': 'Mean reversion forecast',
  'trend-slope-v1': 'Trend direction classifier',
  'lstm-price-v1': 'LSTM forecast placeholder',
  'sjc-classification-v1': 'SJC direction classifier',
  'lstm-k10-price-v1': 'LSTM K10 price forecast',
  'best-gru-price-v1': 'Best GRU price forecast',
  'best-gru-base-price-v1': 'Best GRU base forecast',
  'best-knn-price-v1': 'Best KNN price forecast',
  'bagged-knn-price-v1': 'Bagged KNN price forecast',
  'meta-price-v1': 'Meta price ensemble',
  'meta-lstm-k10-price-v1': 'Meta LSTM K10 ensemble',
};

export function getUserFacingModelLabel(model?: Pick<ModelRead, 'code' | 'name'> | null): string {
  if (!model) {
    return 'N/A';
  }
  return friendlyLabels[model.code] ?? model.name;
}

export function getAdminModelLabel(model?: Pick<ModelRead, 'code' | 'name'> | null): string {
  if (!model) {
    return 'N/A';
  }
  return model.name;
}
