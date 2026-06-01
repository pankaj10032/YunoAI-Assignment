import React, { useMemo, useState } from "react";

/* ── helpers ──────────────────────────────────────────────── */

/**
 * Returns true if the cron string is structurally valid (5 fields).
 * Does a lightweight validation sufficient for the UI preview.
 */
function validateCron(expr) {
  if (!expr || !expr.trim()) return { valid: false, error: "Expression is empty" };
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return { valid: false, error: "Must have exactly 5 fields: min hour dom month dow" };

  const ranges = [
    { min: 0, max: 59 }, // minute
    { min: 0, max: 23 }, // hour
    { min: 1, max: 31 }, // day-of-month
    { min: 1, max: 12 }, // month
    { min: 0, max: 7 },  // day-of-week
  ];

  for (let i = 0; i < 5; i++) {
    const p = parts[i];
    if (p === "*") continue;
    const step = p.match(/^\*\/(\d+)$/);
    if (step) {
      const v = parseInt(step[1], 10);
      if (v < 1 || v > ranges[i].max)
        return { valid: false, error: `Field ${i + 1}: step value out of range` };
      continue;
    }
    const num = parseInt(p, 10);
    if (Number.isNaN(num) || num < ranges[i].min || num > ranges[i].max)
      return { valid: false, error: `Field ${i + 1}: "${p}" is not valid` };
  }
  return { valid: true, error: null };
}

/**
 * Compute next N fire times (approximation) from cron + timezone.
 * Handles the most common patterns: *, */N, exact minute/hour combos.
 */
function computeNextN(cron, tz, n = 5) {
  try {
    const parts = cron.trim().split(/\s+/);
    const [minP, hourP] = parts;
    const results = [];
    let cursor = new Date();
    cursor.setSeconds(0, 0);
    cursor = new Date(cursor.getTime() + 60_000); // start 1 min from now

    const toLocal = (d) =>
      d.toLocaleString("en-US", {
        timeZone: tz,
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });

    // Fully wildcard: every minute
    if (minP === "*" && hourP === "*") {
      for (let i = 0; i < n; i++) {
        results.push(toLocal(cursor));
        cursor = new Date(cursor.getTime() + 60_000);
      }
      return results;
    }

    // Step on minutes: */N
    const minStep = minP.match(/^\*\/(\d+)$/);
    if (minStep && hourP === "*") {
      const step = parseInt(minStep[1], 10);
      const nextMin = Math.ceil(cursor.getMinutes() / step) * step;
      cursor.setMinutes(nextMin % 60, 0, 0);
      for (let i = 0; i < n; i++) {
        results.push(toLocal(cursor));
        cursor = new Date(cursor.getTime() + step * 60_000);
      }
      return results;
    }

    // Step on hours: 0 */N
    const hourStep = hourP.match(/^\*\/(\d+)$/);
    if (minP === "0" && hourStep) {
      const step = parseInt(hourStep[1], 10);
      cursor.setMinutes(0, 0, 0);
      if (cursor <= new Date()) cursor.setHours(cursor.getHours() + step);
      for (let i = 0; i < n; i++) {
        results.push(toLocal(cursor));
        cursor = new Date(cursor.getTime() + step * 3_600_000);
      }
      return results;
    }

    // Exact minute + wildcard hour (every hour at min M)
    const exactMin = parseInt(minP, 10);
    if (!Number.isNaN(exactMin) && hourP === "*") {
      const base = new Date(cursor);
      if (base.getMinutes() >= exactMin) base.setHours(base.getHours() + 1);
      base.setMinutes(exactMin, 0, 0);
      for (let i = 0; i < n; i++) {
        results.push(toLocal(base));
        base.setHours(base.getHours() + 1);
      }
      return results;
    }

    // Exact minute + exact hour (once per day)
    const exactHour = parseInt(hourP, 10);
    if (!Number.isNaN(exactMin) && !Number.isNaN(exactHour)) {
      const base = new Date(cursor);
      base.setHours(exactHour, exactMin, 0, 0);
      if (base <= new Date()) base.setDate(base.getDate() + 1);
      for (let i = 0; i < n; i++) {
        results.push(toLocal(base));
        base.setDate(base.getDate() + 1);
      }
      return results;
    }
  } catch (_) {
    // fall through
  }
  return [];
}

/* ── Full timezone list ───────────────────────────────────── */
const ALL_TIMEZONES = (() => {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch (_) {
    // Fallback for browsers that don't support Intl.supportedValuesOf
    return [
      "UTC",
      "America/New_York",
      "America/Chicago",
      "America/Denver",
      "America/Los_Angeles",
      "America/Sao_Paulo",
      "Europe/London",
      "Europe/Paris",
      "Europe/Berlin",
      "Asia/Kolkata",
      "Asia/Tokyo",
      "Asia/Shanghai",
      "Asia/Singapore",
      "Australia/Sydney",
      "Pacific/Auckland",
    ];
  }
})();

/* ── Component ────────────────────────────────────────────── */
export default function ScheduleConfig({
  initial = { cron: "0 * * * *", timezone: "UTC" },
  onChange,
}) {
  const [cron, setCron] = useState(initial.cron);
  const [timezone, setTimezone] = useState(initial.timezone || "UTC");
  const [tzFilter, setTzFilter] = useState("");

  const cronStatus = useMemo(() => validateCron(cron), [cron]);
  const nextRuns = useMemo(
    () => (cronStatus.valid ? computeNextN(cron, timezone, 5) : []),
    [cron, timezone, cronStatus.valid],
  );

  const filteredTz = useMemo(
    () =>
      tzFilter.trim()
        ? ALL_TIMEZONES.filter((tz) =>
            tz.toLowerCase().includes(tzFilter.toLowerCase()),
          )
        : ALL_TIMEZONES,
    [tzFilter],
  );

  function handleCronChange(e) {
    const val = e.target.value;
    setCron(val);
    if (validateCron(val).valid) onChange?.({ cron: val, timezone });
  }

  function handleTzChange(e) {
    const val = e.target.value;
    setTimezone(val);
    if (cronStatus.valid) onChange?.({ cron, timezone: val });
  }

  return (
    <div className="schedule-config">
      {/* Cron input */}
      <div className="schedule-field">
        <label className="schedule-label" htmlFor="cron-input">
          Cron Expression
          <span className="schedule-hint">min hour dom month dow</span>
        </label>
        <input
          id="cron-input"
          className={`schedule-input${cronStatus.valid ? "" : " schedule-input--error"}`}
          value={cron}
          onChange={handleCronChange}
          placeholder="0 * * * *"
          spellCheck={false}
        />
        {!cronStatus.valid && cron.trim() && (
          <p className="schedule-error-msg">⚠ {cronStatus.error}</p>
        )}
        {cronStatus.valid && (
          <p className="schedule-valid-msg">✓ Valid expression</p>
        )}
      </div>

      {/* Timezone filter + select */}
      <div className="schedule-field">
        <label className="schedule-label" htmlFor="tz-filter">
          Timezone
        </label>
        <input
          id="tz-filter"
          className="schedule-input"
          placeholder="Filter timezones…"
          value={tzFilter}
          onChange={(e) => setTzFilter(e.target.value)}
        />
        <select
          id="tz-select"
          className="schedule-input"
          style={{ marginTop: 6 }}
          value={timezone}
          onChange={handleTzChange}
          size={4}
        >
          {filteredTz.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </div>

      {/* Next 5 fire times */}
      {nextRuns.length > 0 && (
        <div className="schedule-preview">
          <p className="schedule-preview-title">Next 5 scheduled runs:</p>
          <ol className="schedule-preview-list">
            {nextRuns.map((t, i) => (
              <li key={i} className="schedule-preview-item">
                <span className="schedule-preview-num">{i + 1}.</span> {t}
              </li>
            ))}
          </ol>
        </div>
      )}

      {!cronStatus.valid && cron.trim() && (
        <div className="schedule-preview schedule-preview--empty">
          Fix the cron expression to see the next run times.
        </div>
      )}
    </div>
  );
}
