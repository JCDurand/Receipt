import { useLayoutEffect, useRef, useState } from "react";
import { formatMoney } from "../utils/format";
import "../styles/Analytics.css";

/* Categorical colours, in a fixed order (the validated reference palette) */
export const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
export const colorAt = (i) => SERIES_COLORS[i % SERIES_COLORS.length];
/* What a folded-together "Other" is drawn in, so that it never looks like a real series */
export const OTHER_COLOR = "#8b95a1";
export const seriesColor = (id, i) => (id === "__other" ? OTHER_COLOR : colorAt(i));

/* The charts are drawn at the size they are shown, one unit to a pixel, so that
   their text is the same size however wide the card is. W is only the width to
   start from, until the chart has been measured; H is the height. */
const W = 640;
const H = 280;
const PAD = { top: 12, right: 12, bottom: 28, left: 64 };

/* A round number at or above the largest value, for the top of an axis */
const niceMax = (max) => {
  if (max <= 0) return 100;
  const mag = 10 ** Math.floor(Math.log10(max));
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((v) => v >= max);
};

const axisMoney = (cents) => formatMoney(cents, { maximumFractionDigits: 0 });

/* Props which make an element a button which selects `item`, when there is a handler */
const clickable = (onSelect, item) =>
  onSelect
    ? {
        role: "button",
        tabIndex: 0,
        onClick: () => onSelect(item),
        onKeyDown: (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(item);
          }
        },
      }
    : {};

/* A ref for a chart's <svg> and the width it is shown at, kept up to date as it is resized */
const useChartWidth = () => {
  const ref = useRef(null);
  const [width, setWidth] = useState(W);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.max(280, Math.round(entry.contentRect.width));
      setWidth((prev) => (Math.abs(prev - next) >= 1 ? next : prev));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
};

/* ---- Pie and donut ---- */

const polar = (cx, cy, r, angle) => [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];

export const PieChart = ({ slices, donut = false, onSelect }) => {
  const [hover, setHover] = useState(null);
  const total = slices.reduce((s, x) => s + x.cents, 0);
  if (total <= 0) return null;

  const cx = 110;
  const cy = 110;
  const r = 100;
  const inner = donut ? 58 : 0;
  let angle = -Math.PI / 2;

  const arcs = slices.map((slice, i) => {
    const sweep = (slice.cents / total) * Math.PI * 2;
    const start = angle;
    angle += sweep;
    const end = start + Math.min(sweep, Math.PI * 2 - 0.0001);
    const [x1, y1] = polar(cx, cy, r, start);
    const [x2, y2] = polar(cx, cy, r, end);
    const large = sweep > Math.PI ? 1 : 0;
    let d;
    if (donut) {
      const [x3, y3] = polar(cx, cy, inner, end);
      const [x4, y4] = polar(cx, cy, inner, start);
      d = `M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} L${x3},${y3} A${inner},${inner} 0 ${large} 0 ${x4},${y4} Z`;
    } else {
      d = `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} Z`;
    }
    return { slice, d, color: seriesColor(slice.id, i) };
  });

  const shown = hover != null ? slices[hover] : null;

  return (
    <div className="chart-pie">
      <svg viewBox="0 0 220 220" role="img" aria-label="Spending by tag" className="chart-pie-svg">
        {arcs.map(({ slice, d, color }, i) => (
          <path
            key={slice.id}
            d={d}
            fill={color}
            stroke="#fff"
            strokeWidth="2"
            opacity={hover == null || hover === i ? 1 : 0.45}
            style={onSelect ? { cursor: "pointer" } : undefined}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onClick={onSelect ? () => onSelect(slice) : undefined}
          >
            <title>{`${slice.name}: ${formatMoney(slice.cents)} (${((slice.cents / total) * 100).toFixed(1)}%)`}</title>
          </path>
        ))}
        {donut && (
          <g textAnchor="middle" className="chart-center">
            <text x={cx} y={cy - 4} className="chart-center-value">
              {formatMoney(shown ? shown.cents : total)}
            </text>
            <text x={cx} y={cy + 14} className="chart-center-label">
              {shown ? shown.name : "Total"}
            </text>
          </g>
        )}
      </svg>
      <ul className="chart-legend">
        {slices.map((slice, i) => (
          <li
            key={slice.id}
            className={`${hover === i ? "is-hover" : ""}${onSelect ? " is-clickable" : ""}`}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            {...clickable(onSelect, slice)}
          >
            <span className="chart-swatch" style={{ background: seriesColor(slice.id, i) }} />
            <span className="chart-legend-name">{slice.name}</span>
            <span className="chart-legend-value">
              {formatMoney(slice.cents)} · {((slice.cents / total) * 100).toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/* ---- Horizontal bars, one per category ---- */

export const CategoryBars = ({ slices, onSelect }) => {
  const biggest = Math.max(1, ...slices.map((s) => s.cents));
  return (
    <ul className="chart-hbars">
      {slices.map((slice, i) => (
        <li
          key={slice.id}
          title={`${slice.name}: ${formatMoney(slice.cents)}`}
          className={onSelect ? "is-clickable" : undefined}
          {...clickable(onSelect, slice)}
        >
          <span className="chart-hbar-name">{slice.name}</span>
          <span className="chart-hbar-track">
            <span style={{ width: `${(slice.cents / biggest) * 100}%`, background: seriesColor(slice.id, i) }} />
          </span>
          <span className="chart-hbar-value">{formatMoney(slice.cents)}</span>
        </li>
      ))}
    </ul>
  );
};

/* ---- Axes shared by the line and bar charts ---- */

const Axes = ({ min, max, points, x, tick = axisMoney, w = W }) => {
  const ticks = [0, 1, 2, 3, 4].map((i) => min + ((max - min) * i) / 4);
  const y = (v) => PAD.top + (1 - (v - min) / (max - min || 1)) * (H - PAD.top - PAD.bottom);
  /* about six labels along the bottom */
  const every = Math.max(1, Math.ceil(points.length / 6));
  return (
    <g className="chart-axes">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={w - PAD.right} y1={y(t)} y2={y(t)} className="chart-grid" />
          <text x={PAD.left - 8} y={y(t) + 4} textAnchor="end">
            {tick(t)}
          </text>
        </g>
      ))}
      {points.map(
        (p, i) =>
          i % every === 0 && (
            <text key={p.key || p.date} x={x(i)} y={H - 8} textAnchor="middle">
              {p.short}
            </text>
          )
      )}
    </g>
  );
};

/* Points are { key, label, short, cents }; the tooltip follows the pointer's nearest point */
const useNearest = (count, xAt, w = W) => {
  const [index, setIndex] = useState(null);
  const onMove = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * w;
    let best = 0;
    for (let i = 1; i < count; i++) if (Math.abs(xAt(i) - px) < Math.abs(xAt(best) - px)) best = i;
    setIndex(best);
  };
  return [index, { onMouseMove: onMove, onMouseLeave: () => setIndex(null) }];
};

/* A heading line and then a value per line; the box grows to fit them */
const Tooltip = ({ x, y, lines, w = W }) => {
  const width = 170;
  const height = 8 + lines.length * 15;
  const left = Math.min(Math.max(x - width / 2, 4), w - width - 4);
  const top = Math.min(Math.max(y - height - 8, 2), H - height - 2);
  return (
    <g pointerEvents="none" className="chart-tip">
      <rect x={left} y={top} width={width} height={height} rx="0" />
      {lines.map((line, i) => (
        <text key={i} x={left + 8} y={top + 15 + i * 15} className={i ? "chart-tip-value" : undefined}>
          {line}
        </text>
      ))}
    </g>
  );
};

export const BarChart = ({ points, color = SERIES_COLORS[0], label = "Spending over time" }) => {
  const [chartRef, W] = useChartWidth();
  const max = niceMax(Math.max(...points.map((p) => p.cents), 0));
  const inner = W - PAD.left - PAD.right;
  const slot = inner / points.length;
  const xAt = (i) => PAD.left + slot * (i + 0.5);
  const [index, handlers] = useNearest(points.length, xAt, W);
  const y = (v) => PAD.top + (1 - v / max) * (H - PAD.top - PAD.bottom);
  const barW = Math.max(2, Math.min(32, slot - 2));

  return (
    <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label={label} {...handlers}>
      <Axes min={0} max={max} points={points} x={xAt} w={W} />
      {points.map((p, i) => (
        <rect
          key={p.key}
          x={xAt(i) - barW / 2}
          y={y(p.cents)}
          width={barW}
          height={Math.max(0, y(0) - y(p.cents))}
          fill={color}
          opacity={index == null || index === i ? 1 : 0.5}
        />
      ))}
      {index != null && (
        <Tooltip w={W} x={xAt(index)} y={y(points[index].cents)} lines={[points[index].label, formatMoney(points[index].cents)]} />
      )}
    </svg>
  );
};

export const LineChart = ({ points, color = SERIES_COLORS[0], allowNegative = false, area = false }) => {
  const [chartRef, W] = useChartWidth();
  const values = points.map((p) => p.cents);
  const lo = allowNegative ? Math.min(0, ...values) : 0;
  const hi = Math.max(0, ...values);
  const max = niceMax(hi - (allowNegative ? 0 : 0));
  const min = lo < 0 ? -niceMax(-lo) : 0;
  const inner = W - PAD.left - PAD.right;
  const xAt = (i) => (points.length === 1 ? PAD.left + inner / 2 : PAD.left + (inner * i) / (points.length - 1));
  const y = (v) => PAD.top + (1 - (v - min) / (max - min || 1)) * (H - PAD.top - PAD.bottom);
  const [index, handlers] = useNearest(points.length, xAt, W);
  const path = points.map((p, i) => `${i ? "L" : "M"}${xAt(i)},${y(p.cents)}`).join(" ");

  return (
    <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label="Trend" {...handlers}>
      <Axes min={min} max={max} points={points} x={xAt} w={W} />
      {area && points.length > 1 && (
        <path d={`${path} L${xAt(points.length - 1)},${y(min)} L${xAt(0)},${y(min)} Z`} fill={color} opacity="0.12" />
      )}
      <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {points.length <= 40 &&
        points.map((p, i) => <circle key={p.key} cx={xAt(i)} cy={y(p.cents)} r="3" fill={color} stroke="#fff" strokeWidth="2" />)}
      {index != null && (
        <>
          <line x1={xAt(index)} x2={xAt(index)} y1={PAD.top} y2={H - PAD.bottom} className="chart-crosshair" />
          <circle cx={xAt(index)} cy={y(points[index].cents)} r="5" fill={color} stroke="#fff" strokeWidth="2" />
          <Tooltip w={W} x={xAt(index)} y={y(points[index].cents)} lines={[points[index].label, formatMoney(points[index].cents)]} />
        </>
      )}
    </svg>
  );
};

/* Two measures side by side in each bucket, on one axis: `series` are
   [{ field, name, color }] and points carry a value in cents for each field.
   The tooltip adds `extra(point)` lines (the net, say) beneath them. */
export const GroupedBarChart = ({ points, series, label, extra = () => [] }) => {
  const [chartRef, W] = useChartWidth();
  const max = niceMax(Math.max(0, ...points.flatMap((p) => series.map((s) => p[s.field]))));
  const inner = W - PAD.left - PAD.right;
  const slot = inner / points.length;
  const xAt = (i) => PAD.left + slot * (i + 0.5);
  const [index, handlers] = useNearest(points.length, xAt, W);
  const y = (v) => PAD.top + (1 - v / max) * (H - PAD.top - PAD.bottom);
  /* bars in a group touch but for a 2px gap, and groups are kept apart */
  const barW = Math.max(1, Math.min(18, (slot * 0.8 - 2 * (series.length - 1)) / series.length));
  const groupW = barW * series.length + 2 * (series.length - 1);

  return (
    <div>
      <ul className="chart-legend chart-legend-row">
        {series.map((s) => (
          <li key={s.field}>
            <span className="chart-swatch" style={{ background: s.color }} />
            <span className="chart-legend-name">{s.name}</span>
          </li>
        ))}
      </ul>
      <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label={label} {...handlers}>
        <Axes min={0} max={max} points={points} x={xAt} w={W} />
        {points.map((p, i) =>
          series.map((s, j) => (
            <rect
              key={`${p.key}-${s.field}`}
              x={xAt(i) - groupW / 2 + j * (barW + 2)}
              y={y(p[s.field])}
              width={barW}
              height={Math.max(0, y(0) - y(p[s.field]))}
              fill={s.color}
              opacity={index == null || index === i ? 1 : 0.5}
            />
          ))
        )}
        {index != null && (
          <Tooltip
            w={W}
            x={xAt(index)}
            y={y(Math.max(...series.map((s) => points[index][s.field])))}
            lines={[
              points[index].label,
              ...series.map((s) => `${s.name}: ${formatMoney(points[index][s.field])}`),
              ...extra(points[index]),
            ]}
          />
        )}
      </svg>
    </div>
  );
};

/* A share of a whole as a bar, for budgets: `share` is 0..1 or past it, and
   `tone` one of the status colours */
export const STATUS_COLORS = { good: "#2f8f5e", warning: "#d9a12b", serious: "#d9774a", critical: "#c2413a" };

export const ProgressBar = ({ share, tone, marker }) => (
  <span className="chart-progress" role="presentation">
    <span style={{ width: `${Math.min(1, share) * 100}%`, background: STATUS_COLORS[tone] }} />
    {marker != null && marker > 0 && marker <= 1.5 && (
      <i className="chart-progress-marker" style={{ left: `${(Math.min(marker, 1) * 100).toFixed(1)}%` }} />
    )}
  </span>
);

/* ---- Bars divided into labelled parts, one bar per group ---- */

/* groups: [{ id, name, cents, segments: [{ id, name, cents }] }] and `labels`
   (as groupLines gives them) name the parts and fix their colours. A bar, and
   each part of it, can be clicked: `onSelect(group)`. */
export const StackedBars = ({ groups, labels, onSelect }) => {
  const biggest = Math.max(1, ...groups.map((g) => g.cents));
  const showParts = labels.length > 1 || (labels[0] && labels[0].id !== "total");
  const colorOf = (id) => {
    const i = labels.findIndex((l) => l.id === id);
    return seriesColor(id, i < 0 ? 0 : i);
  };
  return (
    <div>
      {showParts && (
        <ul className="chart-legend chart-legend-row">
          {labels.map((l, i) => (
            <li key={l.id}>
              <span className="chart-swatch" style={{ background: seriesColor(l.id, i) }} />
              <span className="chart-legend-name">{l.name}</span>
            </li>
          ))}
        </ul>
      )}
      <ul className="chart-hbars chart-stacked">
        {groups.map((g) => (
          <li
            key={g.id}
            className={onSelect ? "is-clickable" : undefined}
            title={`${g.name}: ${formatMoney(g.cents)}`}
            {...clickable(onSelect, g)}
          >
            <span className="chart-hbar-name">{g.name}</span>
            <span className="chart-hbar-track">
              <span className="chart-stack" style={{ width: `${(g.cents / biggest) * 100}%` }}>
                {showParts
                  ? [...g.segments]
                      .sort((a, b) => labels.findIndex((l) => l.id === a.id) - labels.findIndex((l) => l.id === b.id))
                      .map((seg) => (
                        <i
                          key={seg.id}
                          style={{ width: `${(seg.cents / g.cents) * 100}%`, background: colorOf(seg.id) }}
                          title={`${g.name} · ${seg.name}: ${formatMoney(seg.cents)}`}
                        />
                      ))
                  : <i style={{ width: "100%", background: seriesColor(g.id, groups.indexOf(g)) }} />}
              </span>
            </span>
            <span className="chart-hbar-value">{formatMoney(g.cents)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

/* ---- Columns divided into series, one column per day, week or month ---- */

/* points: [{ key, label, short, values: { [seriesId]: number }, totalCents }],
   series: [{ id, name, color? }]. `format` writes a value (money, by default;
   a count for a histogram of documents), and `onSelect(series)` makes a legend
   entry clickable. */
export const StackedColumns = ({ points, series, label, format = formatMoney, tick, onSelect, counts = false }) => {
  const [chartRef, W] = useChartWidth();
  const peak = Math.max(0, ...points.map((p) => p.totalCents));
  /* counts are whole numbers, so the axis steps in whole numbers too */
  const max = counts ? Math.max(4, Math.ceil(peak / 4) * 4) : niceMax(peak);
  const inner = W - PAD.left - PAD.right;
  const slot = inner / Math.max(1, points.length);
  const xAt = (i) => PAD.left + slot * (i + 0.5);
  const [index, handlers] = useNearest(points.length, xAt, W);
  const y = (v) => PAD.top + (1 - v / max) * (H - PAD.top - PAD.bottom);
  const barW = Math.max(2, Math.min(36, slot - 2));
  const colorOf = (s, i) => s.color || seriesColor(s.id, i);

  return (
    <div>
      <ul className="chart-legend chart-legend-row">
        {series.map((s, i) => (
          <li key={s.id} className={onSelect ? "is-clickable" : undefined} {...clickable(onSelect, s)}>
            <span className="chart-swatch" style={{ background: colorOf(s, i) }} />
            <span className="chart-legend-name">{s.name}</span>
          </li>
        ))}
      </ul>
      <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label={label} {...handlers}>
        <Axes min={0} max={max} points={points} x={xAt} tick={counts ? (n) => String(Math.round(n)) : tick} w={W} />
        {points.map((p, i) => {
          let top = 0;
          return series.map((s, j) => {
            const value = p.values[s.id] || 0;
            if (value <= 0) return null;
            const from = top;
            top += value;
            return (
              <rect
                key={`${p.key}-${s.id}`}
                x={xAt(i) - barW / 2}
                y={y(top)}
                width={barW}
                height={Math.max(0, y(from) - y(top))}
                fill={colorOf(s, j)}
                opacity={index == null || index === i ? 1 : 0.5}
              />
            );
          });
        })}
        {index != null && points[index].totalCents > 0 && (
          <Tooltip
            w={W}
            x={xAt(index)}
            y={y(points[index].totalCents)}
            lines={[
              points[index].label,
              ...series
                .filter((s) => points[index].values[s.id])
                .slice(0, 6)
                .map((s) => `${s.name}: ${format(points[index].values[s.id])}`),
              `Total: ${format(points[index].totalCents)}`,
            ]}
          />
        )}
      </svg>
    </div>
  );
};

/* ---- Several lines on one chart, with levels to compare against ---- */

/* series: [{ id, name, color, dashed?, points: [{ key, label, short, cents }] }],
   all over the same keys; a point with null `cents` is a gap in the line.
   levels: [{ cents, label, color }] are horizontal lines, a budget's target
   say. The tooltip lists every series which has a value at the pointer. */
export const MultiLineChart = ({ series, levels = [], markers = [], label = "Trend" }) => {
  const [chartRef, W] = useChartWidth();
  const keys = series[0]?.points || [];
  const values = [...series.flatMap((s) => s.points.map((p) => p.cents)).filter((c) => c != null), ...levels.map((l) => l.cents)];
  const lo = Math.min(0, ...values);
  const max = niceMax(Math.max(0, ...values));
  const min = lo < 0 ? -niceMax(-lo) : 0;
  const inner = W - PAD.left - PAD.right;
  const xAt = (i) => (keys.length === 1 ? PAD.left + inner / 2 : PAD.left + (inner * i) / Math.max(1, keys.length - 1));
  const y = (v) => PAD.top + (1 - (v - min) / (max - min || 1)) * (H - PAD.top - PAD.bottom);
  const [index, handlers] = useNearest(keys.length, xAt, W);

  return (
    <div>
      <ul className="chart-legend chart-legend-row">
        {series.map((s) => (
          <li key={s.id}>
            <span className="chart-swatch" style={{ background: s.color }} />
            <span className="chart-legend-name">{s.name}</span>
          </li>
        ))}
        {levels.map((l) => (
          <li key={l.label}>
            <span className="chart-swatch chart-swatch-line" style={{ borderColor: l.color }} />
            <span className="chart-legend-name">{l.label}</span>
          </li>
        ))}
      </ul>
      <svg ref={chartRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img" aria-label={label} {...handlers}>
        <Axes min={min} max={max} points={keys} x={xAt} w={W} />
        {/* moments to mark, at the point with their key: a dashed upright line and a label */}
        {markers.map((m) => {
          const at = keys.findIndex((p) => p.key === m.key);
          if (at < 0) return null;
          return (
            <g key={`marker-${m.key}-${m.label}`} className="chart-marker">
              <line x1={xAt(at)} x2={xAt(at)} y1={PAD.top} y2={H - PAD.bottom} stroke={m.color} strokeWidth="1.5" strokeDasharray="3 3" />
              {/* to the left of the line near the right-hand edge, so the label is never cut off */}
              <text
                x={xAt(at) > W - 140 ? xAt(at) - 4 : xAt(at) + 4}
                y={PAD.top + 10}
                fill={m.color}
                fontSize="10"
                textAnchor={xAt(at) > W - 140 ? "end" : "start"}
              >
                {m.label}
              </text>
            </g>
          );
        })}
        {levels.map((l) => (
          <line
            key={l.label}
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(l.cents)}
            y2={y(l.cents)}
            stroke={l.color}
            strokeWidth="1.5"
            strokeDasharray="6 4"
          />
        ))}
        {series.map((s) => (
          <g key={s.id}>
            <path
              d={s.points
                .map((p, i) => (p.cents == null ? null : `${i && s.points[i - 1].cents != null ? "L" : "M"}${xAt(i)},${y(p.cents)}`))
                .filter(Boolean)
                .join(" ")}
              fill="none"
              stroke={s.color}
              strokeWidth="2"
              strokeDasharray={s.dashed ? "5 4" : undefined}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {(!s.dashed || s.dots) &&
              s.points.length <= 24 &&
              s.points.map((p, i) =>
                p.cents == null ? null : (
                  <circle key={p.key} cx={xAt(i)} cy={y(p.cents)} r={s.dots ? 4.5 : 3} fill={s.color} stroke="#fff" strokeWidth="2" />
                )
              )}
          </g>
        ))}
        {index != null && (
          <>
            <line x1={xAt(index)} x2={xAt(index)} y1={PAD.top} y2={H - PAD.bottom} className="chart-crosshair" />
            <Tooltip
              w={W}
              x={xAt(index)}
              y={y(Math.max(0, ...series.map((s) => s.points[index].cents ?? 0)))}
              lines={[
                keys[index].label,
                ...series.filter((s) => s.points[index].cents != null).map((s) => `${s.name}: ${formatMoney(s.points[index].cents)}`),
              ]}
            />
          </>
        )}
      </svg>
    </div>
  );
};
