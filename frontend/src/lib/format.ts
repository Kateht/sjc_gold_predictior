const currencyVnd = new Intl.NumberFormat('vi-VN', {
  style: 'currency',
  currency: 'VND',
  maximumFractionDigits: 0,
});

const domesticPriceFormatter = new Intl.NumberFormat('vi-VN', {
  maximumFractionDigits: 2,
});

const compactNumber = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat('vi-VN', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function formatVnd(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return currencyVnd.format(value);
}

export function formatDomesticPrice(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return `${domesticPriceFormatter.format(value)} triệu VND/lượng`;
}

export function formatUsd(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  return compactNumber.format(value);
}

export function formatPercent(value?: number | null): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'N/A';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) {
    return 'N/A';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return dateFormatter.format(parsed);
}
