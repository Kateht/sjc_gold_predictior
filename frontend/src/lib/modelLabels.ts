import type { ModelRead } from '@/types';

const friendlyLabels: Record<string, string> = {
  'best-xgb-price-v1': 'Best XGBoost price forecast',
  'sjc-classification-v1': 'SJC direction classifier',
  'lstm-k10-price-v1': 'LSTM K10 price forecast',
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
