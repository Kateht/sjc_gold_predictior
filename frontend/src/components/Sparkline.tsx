import { useId, useState } from 'react';

interface SparklineProps {
  values: number[];
  labels?: string[];
  accent?: string;
  height?: number;
  className?: string;
  highlightIndex?: number | null;
  onPointSelect?: (index: number) => void;
  onPointHover?: (index: number | null) => void;
}

export function Sparkline({ values, labels, accent = '#c9921d', height = 128, className, highlightIndex = null, onPointSelect, onPointHover }: SparklineProps) {
  const gradientId = useId().replace(/:/g, '_');
  const [tooltipVisible, setTooltipVisible] = useState(false);

  if (!values.length) {
    return <div className={`sparkline sparkline--empty ${className ?? ''}`.trim()}>No data</div>;
  }

  const width = Math.min(960, Math.max(320, values.length * 4));
  const padding = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const activeIndex = Math.min(Math.max(highlightIndex ?? values.length - 1, 0), values.length - 1);
  const markerStep = values.length > 240 ? 16 : values.length > 180 ? 12 : values.length > 120 ? 8 : values.length > 60 ? 4 : 1;
  const markerRadius = values.length > 180 ? 0.55 : values.length > 90 ? 0.75 : 1;
  const activeRadius = values.length > 180 ? 1.9 : values.length > 90 ? 2.1 : 2.4;
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    return { x, y };
  });
  const linePath = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`;
  const selectedPoint = points[activeIndex];
  const tooltipLabel = labels?.[activeIndex] ?? `Point ${activeIndex + 1}`;
  const tooltipValue = values[activeIndex]?.toLocaleString('en-US', { maximumFractionDigits: 2 }) ?? 'N/A';
  const tooltipLeft = selectedPoint ? `${(selectedPoint.x / width) * 100}%` : '50%';
  const tooltipTop = selectedPoint ? `${Math.max(8, (selectedPoint.y / height) * 100 - 8)}%` : '12%';

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
        <path d={areaPath} fill={`url(#${gradientId})`} />
        <path
          d={linePath}
          fill="none"
          stroke={accent}
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        {points.map((point, index) => (
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
            aria-label={`${labels?.[index] ?? `Point ${index + 1}`}: ${values[index].toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
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
