import React from "react";

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function pathFromPoints(points) {
  if (points.length < 2) return "";
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
}

function cross(origin, first, second) {
  return (
    (first.x - origin.x) * (second.y - origin.y) -
    (first.y - origin.y) * (second.x - origin.x)
  );
}

function convexHull(points) {
  const sorted = [...points].sort((first, second) =>
    first.x === second.x ? first.y - second.y : first.x - second.x,
  );
  if (sorted.length < 3) return sorted;

  const lower = [];
  for (const point of sorted) {
    while (
      lower.length >= 2 &&
      cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0
    ) {
      lower.pop();
    }
    lower.push(point);
  }

  const upper = [];
  for (const point of [...sorted].reverse()) {
    while (
      upper.length >= 2 &&
      cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0
    ) {
      upper.pop();
    }
    upper.push(point);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

function minimumHeightRotation(points) {
  // A minimum-width hull orientation makes the circuit occupy less SVG height.
  const hull = convexHull(points);
  if (hull.length < 2) return 0;

  let bestAngle = 0;
  let smallestHeight = Infinity;
  let widestTie = -Infinity;
  for (let index = 0; index < hull.length; index += 1) {
    const first = hull[index];
    const second = hull[(index + 1) % hull.length];
    const angle = Math.atan2(second.y - first.y, second.x - first.x);
    const cosine = Math.cos(angle);
    const sine = Math.sin(angle);
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const point of hull) {
      const x = point.x * cosine + point.y * sine;
      const y = -point.x * sine + point.y * cosine;
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }

    const height = maxY - minY;
    const width = maxX - minX;
    const tieTolerance = Number.isFinite(smallestHeight)
      ? Math.max(1, smallestHeight) * 1e-8
      : 0;
    if (
      !Number.isFinite(smallestHeight) ||
      height < smallestHeight - tieTolerance ||
      (Math.abs(height - smallestHeight) <= tieTolerance && width > widestTie)
    ) {
      bestAngle = angle;
      smallestHeight = height;
      widestTie = width;
    }
  }
  return bestAngle;
}

function rotatePoint(point, angle) {
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  return {
    x: point.x * cosine + point.y * sine,
    y: -point.x * sine + point.y * cosine,
  };
}

export function Trackmap({
  points = [],
  segments = [],
  corners = [],
  animationKey = "",
  durationMs = 2200,
}) {
  const sourcePoints = points.map((point) => ({
    x: finiteNumber(point.x),
    y: -finiteNumber(point.y),
  }));

  if (sourcePoints.length < 2) return null;

  const sourceCorners = corners.map((corner) => ({
    label: String(corner.label ?? ""),
    trackX: finiteNumber(corner.track_x ?? corner.trackX),
    trackY: -finiteNumber(corner.track_y ?? corner.trackY),
    labelX: finiteNumber(corner.label_x ?? corner.labelX),
    labelY: -finiteNumber(corner.label_y ?? corner.labelY),
  }));
  const rotation = minimumHeightRotation([
    ...sourcePoints,
    ...sourceCorners.flatMap((corner) => [
      { x: corner.trackX, y: corner.trackY },
      { x: corner.labelX, y: corner.labelY },
    ]),
  ]);
  const displayPoints = sourcePoints.map((point) => rotatePoint(point, rotation));
  const displayCorners = sourceCorners.map((corner) => {
    const track = rotatePoint({ x: corner.trackX, y: corner.trackY }, rotation);
    const label = rotatePoint({ x: corner.labelX, y: corner.labelY }, rotation);
    return {
      ...corner,
      trackX: track.x,
      trackY: track.y,
      labelX: label.x,
      labelY: label.y,
    };
  });
  const boundsX = [
    ...displayPoints.map((point) => point.x),
    ...displayCorners.flatMap((corner) => [corner.trackX, corner.labelX]),
  ];
  const boundsY = [
    ...displayPoints.map((point) => point.y),
    ...displayCorners.flatMap((corner) => [corner.trackY, corner.labelY]),
  ];
  const minX = Math.min(...boundsX);
  const maxX = Math.max(...boundsX);
  const minY = Math.min(...boundsY);
  const maxY = Math.max(...boundsY);
  const width = Math.max(maxX - minX, 1);
  const height = Math.max(maxY - minY, 1);
  const scale = Math.max(width, height);
  const padding = scale * 0.055;
  const viewBox = `${minX - padding} ${minY - padding} ${width + padding * 2} ${height + padding * 2}`;
  const fullPath = pathFromPoints(displayPoints);
  const outlineWidth = scale * 0.018;
  const colorWidth = scale * 0.011;
  const markerRadius = scale * 0.014;
  const markerFontSize = scale * 0.016;
  const totalDuration = Math.max(finiteNumber(durationMs, 2200), 0);
  const whiteDuration = totalDuration * 0.55;
  const colorDuration = totalDuration * 0.38;
  const cornerDelay = whiteDuration + colorDuration * 0.82;

  return (
    <svg
      className="trackmap"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Track map colored by the fastest selected lap in each mini-sector"
      style={{
        "--trackmap-white-duration": `${whiteDuration}ms`,
        "--trackmap-color-delay": `${whiteDuration}ms`,
        "--trackmap-color-duration": `${colorDuration}ms`,
        "--trackmap-corner-delay": `${cornerDelay}ms`,
      }}
    >
      <g key={animationKey}>
        <path
          className="trackmap__white-path"
          d={fullPath}
          pathLength="1"
          fill="none"
          stroke="white"
          strokeWidth={outlineWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {segments.map((segment, index) => {
          const start = Math.max(
            0,
            Math.floor(finiteNumber(segment.start_index ?? segment.startIndex)),
          );
          const end = Math.min(
            displayPoints.length - 1,
            Math.floor(finiteNumber(segment.end_index ?? segment.endIndex)),
          );
          const segmentPath = pathFromPoints(displayPoints.slice(start, end + 1));
          return segmentPath ? (
            <path
              className="trackmap__colored-path"
              key={`${segment.winner || "winner"}-${start}-${end}-${index}`}
              d={segmentPath}
              pathLength="1"
              fill="none"
              stroke={segment.color || "white"}
              strokeWidth={colorWidth}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null;
        })}

        <g className="trackmap__corners" aria-hidden="true">
          {displayCorners.map((corner, index) => (
            <g key={`${corner.label}-${index}`}>
              <line
                x1={corner.trackX}
                y1={corner.trackY}
                x2={corner.labelX}
                y2={corner.labelY}
                stroke="var(--gray-9)"
                strokeWidth={scale * 0.0018}
              />
              <circle
                cx={corner.labelX}
                cy={corner.labelY}
                r={markerRadius}
                fill="var(--gray-2)"
                stroke="white"
                strokeWidth={scale * 0.0025}
              />
              <text
                x={corner.labelX}
                y={corner.labelY}
                dy="0.34em"
                textAnchor="middle"
                fill="white"
                fontSize={markerFontSize}
                fontWeight="700"
              >
                {corner.label}
              </text>
            </g>
          ))}
        </g>
      </g>
    </svg>
  );
}
