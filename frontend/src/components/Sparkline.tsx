import { useId, useState } from 'react';

interface SparklineSeries {
  values: number[];
  accent: string;
  label: string;
}

interface SparklineProps {
  values?: number[];
  series?: SparklineSeries[];
  multiAxisMode?: 'shared' | 'dual';
  labels?: string[];
  accent?: string;
  height?: number;
  className?: string;
  highlightIndex?: number | null;
  onPointSelect?: (index: number) => void;
  onPointHover?: (index: number | null) => void;
}

export function Sparkline({
  values,
  series,
  multiAxisMode = 'shared',
  labels,
  accent = '#c9921d',
  height = 128,
  className,
  highlightIndex = null,
  onPointSelect,
  onPointHover,
}: SparklineProps) {
  const gradientId = useId().replace(/:/g, '_');
  const [tooltipVisible, setTooltipVisible] = useState(false);

  const isMultiSeries = Boolean(series?.length);
  const primaryValues = values ?? series?.[0]?.values ?? [];

  if (!primaryValues.length) {
    return <div className={`sparkline sparkline--empty ${className ?? ''}`.trim()}>No data</div>;
  }

  const width = Math.min(960, Math.max(320, primaryValues.length * 4));
  const padding = 8;
  const allSeriesValues = isMultiSeries && multiAxisMode === 'shared'
    ? (series ?? []).flatMap((entry) => entry.values)
    : primaryValues;
  const min = Math.min(...allSeriesValues);
  const max = Math.max(...allSeriesValues);
  const range = max - min || 1;
  const activeIndex = Math.min(Math.max(highlightIndex ?? primaryValues.length - 1, 0), primaryValues.length - 1);
  const markerStep = primaryValues.length > 240 ? 16 : primaryValues.length > 180 ? 12 : primaryValues.length > 120 ? 8 : primaryValues.length > 60 ? 4 : 1;
  const markerRadius = primaryValues.length > 180 ? 0.55 : primaryValues.length > 90 ? 0.75 : 1;
  const activeRadius = primaryValues.length > 180 ? 1.9 : primaryValues.length > 90 ? 2.1 : 2.4;
  const points = primaryValues.map((value, index) => {
    const x = primaryValues.length === 1 ? width / 2 : (index / (primaryValues.length - 1)) * width;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x, y };
  });
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`;
  const selectedPoint = points[activeIndex];
  const tooltipLabel = labels?.[activeIndex] ?? `Point ${activeIndex + 1}`;
  const tooltipValue = isMultiSeries
    ? (series ?? []).map((entry) => `${entry.label}: ${entry.values[activeIndex]?.toLocaleString('en-US', { maximumFractionDigits: 2 }) ?? 'N/A'}`).join(' | ')
    : primaryValues[activeIndex]?.toLocaleString('en-US', { maximumFractionDigits: 2 }) ?? 'N/A';
  const tooltipLeft = selectedPoint ? `${(selectedPoint.x / width) * 100}%` : '50%';
  const tooltipTop = selectedPoint ? `${Math.max(8, (selectedPoint.y / height) * 100 - 8)}%` : '12%';
  const seriesList = series ?? [{ values: primaryValues, accent, label: 'Series' }];

  function handlePointActivate(index: number) {
    setTooltipVisible(true);
    onPointHover?.(index);
    onPointSelect?.(index);
  }

  return (
    <div
      className={`sparkline ${onPointSelect || onPointHover ? 'sparkline--interactive' : ''} ${className ?? ''}`.trim()}
      onMouseLeave={onPointHover ? () => {
        setTooltipVisible(false);
        onPointHover(null);
      } : undefined}
    >
      {tooltipVisible && selectedPoint ? (
        <div className="sparkline__tooltip" style={{ left: tooltipLeft, top: tooltipTop }}>
          <strong>{tooltipValue}</strong>
          <span>{tooltipLabel}</span>
        </div>
      ) : null}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Trend chart"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity="0.35" />
            <stop offset="100%" stopColor={accent} stopOpacity="0.04" />
          </linearGradient>
        </defs>
        {selectedPoint ? (
          <line
            x1={selectedPoint.x}
            y1={padding}
            x2={selectedPoint.x}
            y2={height - padding}
            stroke={accent}
            strokeOpacity="0.18"
            strokeDasharray="3 4"
            vectorEffect="non-scaling-stroke"
          />
        ) : null}
        {!isMultiSeries ? <path d={areaPath} fill={`url(#${gradientId})`} /> : null}
        <path
          d={linePath}
          fill="none"
          stroke={accent}
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        {isMultiSeries ? (
          seriesList.map((entry, seriesIndex) => {
            const seriesMin = multiAxisMode === 'dual' ? Math.min(...entry.values) : min;
            const seriesMax = multiAxisMode === 'dual' ? Math.max(...entry.values) : max;
            const seriesRange = seriesMax - seriesMin || 1;
            const seriesPoints = entry.values.map((value, index) => {
              const x = entry.values.length === 1 ? width / 2 : (index / (entry.values.length - 1)) * width;
              const y = height - padding - ((value - seriesMin) / seriesRange) * (height - padding * 2);
              return { x, y };
            });
            const seriesLinePath = seriesPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
            const seriesAreaPath = `${seriesLinePath} L ${seriesPoints[seriesPoints.length - 1].x} ${height - padding} L ${seriesPoints[0].x} ${height - padding} Z`;
            const seriesActivePoint = seriesPoints[activeIndex];
            return (
              <g key={entry.label}>
                {seriesIndex === 0 ? <path d={seriesAreaPath} fill={entry.accent} fillOpacity="0.04" /> : null}
                <path
                  d={seriesLinePath}
                  fill="none"
                  stroke={entry.accent}
                  strokeWidth={seriesIndex === 0 ? '2.2' : '1.9'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
                {seriesPoints.map((point, index) => (
                  <circle
                    key={`${entry.label}-${point.x}-${point.y}`}
                    cx={point.x}
                    cy={point.y}
                    r={index === activeIndex ? activeRadius : index === seriesPoints.length - 1 || index === 0 || index % markerStep === 0 ? markerRadius : 0}
                    fill={index === activeIndex ? '#fff' : entry.accent}
                    fillOpacity={index === activeIndex ? 1 : 0.9}
                    stroke={entry.accent}
                    strokeWidth={index === activeIndex ? 1.4 : 0}
                    vectorEffect="non-scaling-stroke"
                    tabIndex={onPointSelect || onPointHover ? 0 : undefined}
                    role={onPointSelect || onPointHover ? 'button' : undefined}
                    aria-label={`${entry.label} ${labels?.[index] ?? `Point ${index + 1}`}: ${entry.values[index].toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
                    style={onPointSelect || onPointHover ? { cursor: 'pointer' } : undefined}
                    onMouseEnter={onPointHover ? () => handlePointActivate(index) : undefined}
                    onFocus={onPointHover ? () => handlePointActivate(index) : undefined}
                    onClick={onPointSelect || onPointHover ? () => handlePointActivate(index) : undefined}
                    onKeyDown={onPointSelect || onPointHover ? (event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        handlePointActivate(index);
                      }
                    } : undefined}
                    onBlur={onPointHover ? () => {
                      setTooltipVisible(false);
                      onPointHover(null);
                    } : undefined}
                  />
                ))}
                {seriesActivePoint ? (
                  <line
                    x1={seriesActivePoint.x}
                    y1={padding}
                    x2={seriesActivePoint.x}
                    y2={height - padding}
                    stroke={entry.accent}
                    strokeOpacity="0.08"
                    strokeDasharray="3 4"
                    vectorEffect="non-scaling-stroke"
                  />
                ) : null}
              </g>
            );
          })
        ) : (
          points.map((point, index) => (
            <circle
              key={`${point.x}-${point.y}`}
              cx={point.x}
              cy={point.y}
              r={index === activeIndex ? activeRadius : index === points.length - 1 || index === 0 || index % markerStep === 0 ? markerRadius : 0}
              fill={index === activeIndex ? '#fff' : accent}
              fillOpacity={index === activeIndex ? 1 : 0.9}
              stroke={accent}
              strokeWidth={index === activeIndex ? 1.4 : 0}
              vectorEffect="non-scaling-stroke"
              tabIndex={onPointSelect || onPointHover ? 0 : undefined}
              role={onPointSelect || onPointHover ? 'button' : undefined}
              aria-label={`${labels?.[index] ?? `Point ${index + 1}`}: ${primaryValues[index].toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
              style={onPointSelect || onPointHover ? { cursor: 'pointer' } : undefined}
              onMouseEnter={onPointHover ? () => handlePointActivate(index) : undefined}
              onFocus={onPointHover ? () => handlePointActivate(index) : undefined}
              onClick={onPointSelect || onPointHover ? () => handlePointActivate(index) : undefined}
              onKeyDown={onPointSelect || onPointHover ? (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  handlePointActivate(index);
                }
              } : undefined}
              onBlur={onPointHover ? () => {
                setTooltipVisible(false);
                onPointHover(null);
              } : undefined}
            />
          ))
        )}
      </svg>
      {labels?.length ? (
        <div className="sparkline__labels">
          <span>{labels[0]}</span>
          <span>{labels[labels.length - 1]}</span>
        </div>
      ) : null}
    </div>
  );
}
