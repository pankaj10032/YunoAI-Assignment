import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

export function fuzzyMatch(value = "", query = "") {
  const source = String(value).toLowerCase();
  const needle = String(query).toLowerCase().trim();
  if (!needle) return true;
  if (source.includes(needle)) return true;

  let index = 0;
  for (const char of source) {
    if (char === needle[index]) index += 1;
    if (index === needle.length) return true;
  }
  return false;
}

export function getQueryFilters(searchParams, filterKeys = []) {
  const filters = { q: searchParams.get("q") || "" };
  filterKeys.forEach((key) => {
    filters[key] = searchParams.getAll(key);
  });
  return filters;
}

export default function SearchFilterBar({
  filters,
  groups = [],
  totalCount,
  resultCount,
  emptyLabel = "No results match. Try adjusting filters.",
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [draftQuery, setDraftQuery] = useState(filters.q || "");
  const inputRef = useRef(null);

  useEffect(() => {
    setDraftQuery(filters.q || "");
  }, [filters.q]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      updateParam("q", draftQuery.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [draftQuery, searchParams]);

  useEffect(() => {
    const focusSearch = (event) => {
      const tagName = event.target?.tagName?.toLowerCase();
      const isTyping = ["input", "textarea", "select"].includes(tagName);
      if (event.key === "/" && !isTyping) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const activeChips = useMemo(() => {
    const chips = [];
    if (filters.q) chips.push({ key: "q", value: filters.q, label: `Search: ${filters.q}` });
    groups.forEach((group) => {
      (filters[group.key] || []).forEach((value) => {
        chips.push({
          key: group.key,
          value,
          label: `${group.label}: ${labelForValue(group, value)}`,
        });
      });
    });
    return chips;
  }, [filters, groups]);

  const updateParam = (key, value) => {
    const next = new URLSearchParams(searchParams);
    next.delete(key);
    if (Array.isArray(value)) {
      value.filter(Boolean).forEach((item) => next.append(key, item));
    } else if (value) {
      next.set(key, value);
    }
    if (next.toString() === searchParams.toString()) return;
    setSearchParams(next, { replace: false });
  };

  const toggleTag = (key, value) => {
    const selected = new Set(filters[key] || []);
    if (selected.has(value)) {
      selected.delete(value);
    } else {
      selected.add(value);
    }
    updateParam(key, [...selected]);
  };

  const removeChip = (chip) => {
    if (chip.key === "q") {
      setDraftQuery("");
      updateParam("q", "");
      return;
    }
    updateParam(
      chip.key,
      (filters[chip.key] || []).filter((value) => value !== chip.value),
    );
  };

  const clearAll = () => {
    setDraftQuery("");
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    groups.forEach((group) => next.delete(group.key));
    setSearchParams(next, { replace: false });
  };

  return (
    <section className="rounded-md border border-line bg-surface p-4 transition-colors">
      <div className="grid gap-3 lg:grid-cols-[minmax(220px,1fr)_auto] lg:items-end">
        <label className="space-y-1">
          <span className="text-sm font-medium">Search</span>
          <input
            ref={inputRef}
            type="search"
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
            className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ink/20"
            placeholder="Search by name, role, or description"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          {groups.map((group) => (
            <label key={group.key} className="space-y-1">
              <span className="block text-sm font-medium">{group.label}</span>
              <select
                value=""
                onChange={(event) => {
                  if (event.target.value) toggleTag(group.key, event.target.value);
                  event.target.value = "";
                }}
                className="min-w-36 rounded-md border border-line bg-surface px-3 py-2 text-sm"
              >
                <option value="">Add {group.label}</option>
                {group.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p aria-live="polite" className="text-sm text-muted">
          {resultCount ? `Showing ${resultCount} of ${totalCount}` : emptyLabel}
        </p>

        <div className="flex flex-wrap gap-2">
          {activeChips.map((chip) => (
            <button
              key={`${chip.key}-${chip.value}`}
              type="button"
              onClick={() => removeChip(chip)}
              className="rounded-full border border-line bg-soft px-3 py-1 text-xs font-semibold text-ink transition-colors hover:bg-surface"
            >
              {chip.label} x
            </button>
          ))}
          {activeChips.length ? (
            <button
              type="button"
              onClick={clearAll}
              className="rounded-md border border-line px-3 py-1 text-xs font-semibold transition-colors hover:bg-soft"
            >
              Clear all
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function labelForValue(group, value) {
  return group.options.find((option) => option.value === value)?.label || value;
}