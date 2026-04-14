const currencyVnd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'VND',
  maximumFractionDigits: 0,
});

const domesticPriceFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

const compactNumber = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const shortDateFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
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
  return `${domesticPriceFormatter.format(value)} million VND/tael`;
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

export function formatMarketPrice(value?: number | null, source?: string | null): string {
  const normalizedSource = (source ?? '').trim().toLowerCase();
  if (normalizedSource === 'world' || normalizedSource === 'gc=f' || normalizedSource === 'gc') {
    return formatUsd(value);
  }
  return formatDomesticPrice(value);
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

export function formatDateOnly(value?: string | null): string {
  if (!value) {
    return 'N/A';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return shortDateFormatter.format(parsed);
}
