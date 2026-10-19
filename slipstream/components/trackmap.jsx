import React from "react";
import { ReferenceLine } from "recharts";

const PlaybackContext = React.createContext({
  enabled: false,
  currentTime: 0,
  distance: 0,
});

export function TelemetryPlaybackLine({ distanceMetres = 0 }) {
  const playback = React.useContext(PlaybackContext);
  if (!playback.enabled) return null;

  return (
    <ReferenceLine
      x={Math.min(
        finiteNumber(distanceMetres),
        Math.max(0, finiteNumber(playback.distance)),
      )}
      stroke="var(--accent-9)"
      strokeWidth={2}
      zIndex={500}
      ifOverflow="hidden"
    />
  );
}

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
  preserveOrientation = false,
  animationKey = "",
  durationMs = 2200,
  activePointIndex = 0,
  playbackLaps = [],
}) {
  const geometry = React.useMemo(() => {
    const sourcePoints = points.map((point) => ({
      x: finiteNumber(point.x),
      y: -finiteNumber(point.y),
      distance: finiteNumber(point.distance),
    }));
    if (sourcePoints.length < 2) return null;

    const sourceCorners = corners.map((corner) => ({
      label: String(corner.label ?? ""),
      trackX: finiteNumber(corner.track_x ?? corner.trackX),
      trackY: -finiteNumber(corner.track_y ?? corner.trackY),
      labelX: finiteNumber(corner.label_x ?? corner.labelX),
      labelY: -finiteNumber(corner.label_y ?? corner.labelY),
    }));
    const rotation = preserveOrientation
      ? 0
      : minimumHeightRotation([
          ...sourcePoints,
          ...sourceCorners.flatMap((corner) => [
            { x: corner.trackX, y: corner.trackY },
            { x: corner.labelX, y: corner.labelY },
          ]),
        ]);
    const displayPoints = sourcePoints.map((point) => ({
      ...rotatePoint(point, rotation),
      distance: point.distance,
    }));
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
    const viewBoxWidth = width + padding * 2;
    const viewBoxHeight = height + padding * 2;
    const segmentPaths = segments.map((segment, index) => {
      const start = Math.max(
        0,
        Math.floor(finiteNumber(segment.start_index ?? segment.startIndex)),
      );
      const end = Math.min(
        displayPoints.length - 1,
        Math.floor(finiteNumber(segment.end_index ?? segment.endIndex)),
      );
      return {
        key: String(segment.winner || "winner") + "-" + start + "-" + end + "-" + index,
        path: pathFromPoints(displayPoints.slice(start, end + 1)),
        color: segment.color || "white",
      };
    });
    return {
      displayPoints,
      displayCorners,
      scale,
      viewBoxWidth,
      viewBoxHeight,
      viewBox: (minX - padding) + " " + (minY - padding) + " " + viewBoxWidth + " " + viewBoxHeight,
      fullPath: pathFromPoints(displayPoints),
      segmentPaths,
    };
  }, [points, segments, corners, preserveOrientation]);

  if (!geometry) return null;
  const {
    displayPoints,
    displayCorners,
    scale,
    viewBoxWidth,
    viewBoxHeight,
    viewBox,
    fullPath,
    segmentPaths,
  } = geometry;
  const outlineWidth = scale * 0.018;
  const colorWidth = scale * 0.011;
  const markerRadius = scale * 0.014;
  const markerFontSize = scale * 0.016;
  const positionMarkerRadius = scale * 0.018;
  const positionMarkerIndex = Math.min(
    displayPoints.length - 1,
    Math.max(0, Math.round(finiteNumber(activePointIndex))),
  );
  const positionMarker = displayPoints[positionMarkerIndex];
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
        aspectRatio: `${viewBoxWidth} / ${viewBoxHeight}`,
      }}
    >
      <g key={animationKey}>
        <path
          className="trackmap__white-path"
          d={fullPath}
          pathLength="1"
          fill="none"
          stroke="var(--gray-12)"
          strokeWidth={outlineWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {segmentPaths.map((segment) =>
          segment.path ? (
            <path
              className="trackmap__colored-path"
              key={segment.key}
              d={segment.path}
              pathLength="1"
              fill="none"
              stroke={segment.color}
              strokeWidth={colorWidth}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null
        )}

        <g className="trackmap__corners" aria-hidden="true">
          {displayCorners.map((corner, index) => (
            <g key={`${corner.label}-${index}`}>
              <circle
                cx={corner.labelX}
                cy={corner.labelY}
                r={markerRadius}
                fill="var(--gray-2)"
                stroke="var(--gray-12)"
                strokeWidth={scale * 0.0025}
              />
              <text
                x={corner.labelX}
                y={corner.labelY}
                dy="0.34em"
                textAnchor="middle"
                fill="var(--gray-12)"
                fontSize={markerFontSize}
                fontWeight="700"
              >
                {corner.label}
              </text>
            </g>
          ))}
        </g>

        <circle
          className="trackmap__position-marker"
          cx={positionMarker.x}
          cy={positionMarker.y}
          r={positionMarkerRadius}
          fill="var(--gray-12)"
          aria-hidden="true"
        />
        <TrackmapPlaybackDots
          points={displayPoints}
          playbackLaps={playbackLaps}
          scale={scale}
        />
      </g>
    </svg>
  );
}

function lapPositionAtTime(lap, points, currentTime) {
  const elapsed = lap.elapsed;
  if (currentTime <= 0) return points[0];
  if (currentTime >= lap.duration) return points[points.length - 1];

  let low = 0;
  let high = elapsed.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (elapsed[middle] < currentTime) low = middle + 1;
    else high = middle;
  }

  const upperIndex = Math.max(1, low);
  const lowerIndex = upperIndex - 1;
  const span = elapsed[upperIndex] - elapsed[lowerIndex];
  const fraction =
    span > 0
      ? Math.min(
          1,
          Math.max(0, (currentTime - elapsed[lowerIndex]) / span),
        )
      : 0;
  const first = points[lowerIndex];
  const second = points[upperIndex];
  return {
    x: first.x + (second.x - first.x) * fraction,
    y: first.y + (second.y - first.y) * fraction,
    distance:
      finiteNumber(first.distance) +
      (finiteNumber(second.distance) - finiteNumber(first.distance)) * fraction,
  };
}

function formatPlaybackTime(seconds) {
  const totalTenths = Math.max(
    0,
    Math.round(finiteNumber(seconds) * 10),
  );
  const wholeSeconds = Math.floor(totalTenths / 10);
  const minutes = Math.floor(wholeSeconds / 60);
  return (
    minutes +
    ":" +
    String(wholeSeconds % 60).padStart(2, "0") +
    "." +
    String(totalTenths % 10)
  );
}

function TrackmapPlaybackDots({ points, playbackLaps, scale }) {
  const playback = React.useContext(PlaybackContext);
  if (!playback.enabled) return null;

  return (
    <g className="trackmap__playback-dots" aria-label="Lap playback positions">
      {playbackLaps.map((lap) => {
        const point = lapPositionAtTime(lap, points, playback.currentTime);
        return (
          <circle
            key={lap.key}
            cx={point.x}
            cy={point.y}
            r={scale * 0.018}
            fill={lap.color || "white"}
            className="trackmap__playback-dot"
          >
            <title>{lap.label}</title>
          </circle>
        );
      })}
    </g>
  );
}

function chartPlotBounds(chart) {
  const gridLine = chart.querySelector(
    ".recharts-cartesian-grid-horizontal line",
  );
  const gridBounds = gridLine?.getBoundingClientRect();
  if (gridBounds && gridBounds.width > 0) return gridBounds;

  const surfaceBounds = chart
    .querySelector(".recharts-surface")
    ?.getBoundingClientRect();
  return surfaceBounds?.width > 0 ? surfaceBounds : chart.getBoundingClientRect();
}

const MemoizedTrackmap = React.memo(Trackmap);

export function TelemetryTrackSync({
  points = [],
  segments = [],
  corners = [],
  preserveOrientation = false,
  animationKey = "",
  durationMs = 2200,
  playbackLaps = [],
  playbackKey = "",
  distanceMetres = 0,
  children,
}) {
  const [activePointIndex, setActivePointIndex] = React.useState(0);
  const [currentTime, setCurrentTime] = React.useState(0);
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState(1);
  const currentTimeRef = React.useRef(0);
  const speedRef = React.useRef(1);

  const usablePlaybackLaps = React.useMemo(
    () =>
      playbackLaps.filter(
        (lap) =>
          points.length >= 2 &&
          lap.elapsed?.length === points.length &&
          Number.isFinite(Number(lap.duration)) &&
          Number(lap.duration) > 0 &&
          lap.elapsed.every((value) => Number.isFinite(Number(value))),
      ),
    [playbackLaps, points.length],
  );
  const totalDuration = React.useMemo(
    () =>
      usablePlaybackLaps.reduce(
        (duration, lap) => Math.max(duration, Number(lap.duration)),
        0,
      ),
    [usablePlaybackLaps],
  );
  const playbackEnabled = usablePlaybackLaps.length > 0 && totalDuration > 0;
  const playbackProgress = playbackEnabled
    ? Math.min(1, Math.max(0, currentTime / totalDuration))
    : 0;
  const playbackReferenceLap = playbackEnabled
    ? usablePlaybackLaps.reduce((slowestLap, lap) =>
        Number(lap.duration) > Number(slowestLap.duration) ? lap : slowestLap,
      )
    : null;
  const playbackDistance = playbackReferenceLap
    ? lapPositionAtTime(playbackReferenceLap, points, currentTime).distance
    : 0;
  const playbackContext = React.useMemo(
    () => ({
      enabled: playbackEnabled,
      currentTime,
      distance: playbackDistance,
    }),
    [playbackEnabled, currentTime, playbackDistance],
  );

  React.useEffect(() => {
    // A newly loaded lap always starts with the marker on the finish line.
    setActivePointIndex(0);
  }, [animationKey, points.length]);

  React.useEffect(() => {
    setIsPlaying(false);
    currentTimeRef.current = 0;
    setCurrentTime(0);
    speedRef.current = 1;
    setSpeed(1);
  }, [playbackKey]);

  React.useEffect(() => {
    if (!isPlaying || !playbackEnabled) return undefined;

    let animationFrame = 0;
    let previousTimestamp = null;
    const advance = (timestamp) => {
      if (document.visibilityState === "hidden") {
        setIsPlaying(false);
        return;
      }
      if (previousTimestamp === null) previousTimestamp = timestamp;
      const deltaSeconds = (timestamp - previousTimestamp) / 1000;
      previousTimestamp = timestamp;
      const nextTime = Math.min(
        totalDuration,
        currentTimeRef.current + deltaSeconds * speedRef.current,
      );
      currentTimeRef.current = nextTime;
      setCurrentTime(nextTime);
      if (nextTime >= totalDuration) {
        setIsPlaying(false);
        return;
      }
      animationFrame = window.requestAnimationFrame(advance);
    };

    animationFrame = window.requestAnimationFrame(advance);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [isPlaying, playbackEnabled, totalDuration]);

  React.useEffect(() => {
    const pauseWhenHidden = () => {
      if (document.visibilityState === "hidden") setIsPlaying(false);
    };
    document.addEventListener("visibilitychange", pauseWhenHidden);
    return () => document.removeEventListener("visibilitychange", pauseWhenHidden);
  }, []);

  function togglePlayback() {
    if (isPlaying) {
      setIsPlaying(false);
      return;
    }
    if (currentTimeRef.current >= totalDuration) {
      currentTimeRef.current = 0;
      setCurrentTime(0);
    }
    setIsPlaying(true);
  }

  function seekPlayback(event) {
    const nextTime = Math.min(
      totalDuration,
      Math.max(0, finiteNumber(event.target.value)),
    );
    currentTimeRef.current = nextTime;
    setCurrentTime(nextTime);
  }

  function changeSpeed(speedValue) {
    const nextSpeed = finiteNumber(speedValue, 1);
    speedRef.current = nextSpeed;
    setSpeed(nextSpeed);
  }

  function restartPlayback() {
    currentTimeRef.current = 0;
    setCurrentTime(0);
  }

  function handleMouseMove(event) {
    const target = event.target instanceof Element ? event.target : null;
    const chart = target?.closest(".recharts-wrapper");
    if (!chart || !event.currentTarget.contains(chart) || points.length < 2) return;

    const bounds = chartPlotBounds(chart);
    if (bounds.width <= 0) return;
    const progress = Math.min(
      1,
      Math.max(0, (event.clientX - bounds.left) / bounds.width),
    );
    const nextIndex = Math.round(progress * (points.length - 1));
    setActivePointIndex((currentIndex) =>
      currentIndex === nextIndex ? currentIndex : nextIndex,
    );
  }

  return (
    <PlaybackContext.Provider value={playbackContext}>
      <div className="telemetry-track-sync" onMouseMove={handleMouseMove}>
        <MemoizedTrackmap
          points={points}
          segments={segments}
          corners={corners}
          preserveOrientation={preserveOrientation}
          animationKey={animationKey}
          durationMs={durationMs}
          activePointIndex={activePointIndex}
          playbackLaps={usablePlaybackLaps}
        />
        {playbackEnabled ? (
          <div
            className="telemetry-player"
            role="group"
            aria-label="Selected lap playback"
          >
            <button
              className="telemetry-player__toggle"
              type="button"
              onClick={togglePlayback}
              aria-label={isPlaying ? "Pause playback" : "Play playback"}
              title={isPlaying ? "Pause" : "Play"}
            >
              {isPlaying ? (
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M8 5.5v13L18.5 12 8 5.5z" />
                </svg>
              )}
            </button>
            <button
              className="telemetry-player__restart"
              type="button"
              onClick={restartPlayback}
              aria-label="Restart playback"
              title="Restart"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4.5 8.5A8.5 8.5 0 1 1 4 14" />
                <path d="M4.5 3.5v5h5" />
              </svg>
            </button>
            <div className="telemetry-player__timeline">
              <input
                className="telemetry-player__range"
                type="range"
                min="0"
                max={totalDuration}
                step="0.01"
                value={currentTime}
                onChange={seekPlayback}
                style={{ "--playback-progress": `${playbackProgress * 100}%` }}
                aria-label="Playback position"
                aria-valuetext={
                  formatPlaybackTime(currentTime) +
                  " of " +
                  formatPlaybackTime(totalDuration)
                }
              />
            </div>
            <span className="telemetry-player__time" aria-live="off">
              {formatPlaybackTime(currentTime)} / {formatPlaybackTime(totalDuration)}
            </span>
            <div
              className="telemetry-player__speeds"
              role="group"
              aria-label="Playback speed"
            >
              {[0.5, 1, 2, 4].map((playbackSpeed) => (
                <button
                  key={playbackSpeed}
                  className={
                    "telemetry-player__speed" +
                    (speed === playbackSpeed
                      ? " telemetry-player__speed--active"
                      : "")
                  }
                  type="button"
                  onClick={() => changeSpeed(playbackSpeed)}
                  aria-label={`${playbackSpeed} times speed`}
                  aria-pressed={speed === playbackSpeed}
                >
                  {playbackSpeed}x
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {children}
      </div>
    </PlaybackContext.Provider>
  );
}
