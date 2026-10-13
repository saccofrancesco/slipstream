import React, { useId } from "react";

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

export function CircuitMap({
  points = [],
  segments = [],
  corners = [],
  animationKey = "",
  durationMs = 2500,
}) {
  const maskId = `circuit-map-${useId().replaceAll(":", "")}`;
  const displayPoints = points.map((point) => ({
    x: finiteNumber(point.x),
    y: -finiteNumber(point.y),
  }));

  if (displayPoints.length < 2) return null;

  const displayCorners = corners.map((corner) => ({
    label: String(corner.label ?? ""),
    trackX: finiteNumber(corner.track_x ?? corner.trackX),
    trackY: -finiteNumber(corner.track_y ?? corner.trackY),
    labelX: finiteNumber(corner.label_x ?? corner.labelX),
    labelY: -finiteNumber(corner.label_y ?? corner.labelY),
  }));
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
  const duration = Math.max(finiteNumber(durationMs, 2500), 0);

  return (
    <svg
      className="circuit-map"
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Circuit map colored by the fastest selected lap in each mini-sector"
      style={{ "--circuit-map-duration": `${duration}ms` }}
    >
      <g key={animationKey}>
        <defs>
          <mask id={maskId} maskUnits="userSpaceOnUse" x={minX - padding} y={minY - padding} width={width + padding * 2} height={height + padding * 2}>
            <path
              className="circuit-map__reveal"
              d={fullPath}
              pathLength="1"
              fill="none"
              stroke="white"
              strokeWidth={outlineWidth * 1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </mask>
        </defs>

        <g mask={`url(#${maskId})`}>
          <path
            d={fullPath}
            fill="none"
            stroke="white"
            strokeWidth={outlineWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {segments.map((segment, index) => {
            const start = Math.max(0, Math.floor(finiteNumber(segment.start_index ?? segment.startIndex)));
            const end = Math.min(
              displayPoints.length - 1,
              Math.floor(finiteNumber(segment.end_index ?? segment.endIndex)),
            );
            const segmentPath = pathFromPoints(displayPoints.slice(start, end + 1));
            return segmentPath ? (
              <path
                key={`${start}-${end}-${index}`}
                d={segmentPath}
                fill="none"
                stroke={segment.color || "white"}
                strokeWidth={colorWidth}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            ) : null;
          })}
        </g>

        <g
          className="circuit-map__corners"
          style={{ animationDelay: `${duration * 0.82}ms` }}
          aria-hidden="true"
        >
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
