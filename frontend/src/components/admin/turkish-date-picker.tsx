"use client";

const MONTHS_TR = [
  "Ocak",
  "Şubat",
  "Mart",
  "Nisan",
  "Mayıs",
  "Haziran",
  "Temmuz",
  "Ağustos",
  "Eylül",
  "Ekim",
  "Kasım",
  "Aralık",
];

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate();
}

function pad(value: number) {
  return String(value).padStart(2, "0");
}

function toIso(year: number, month: number, day: number) {
  const max = daysInMonth(year, month);
  const safeDay = Math.min(Math.max(day, 1), max);
  return `${year}-${pad(month)}-${pad(safeDay)}`;
}

function parseIso(value: string) {
  const [year, month, day] = (value || "").split("-").map(Number);
  return {
    year: year || 2026,
    month: month || 1,
    day: day || 1,
  };
}

export function TurkishDatePicker({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled?: boolean;
  onChange: (iso: string) => void;
}) {
  const stamp = parseIso(value);
  const maxDay = daysInMonth(stamp.year, stamp.month);
  const years = Array.from({ length: 10 }, (_, index) => 2025 + index);
  const selectClass =
    "h-10 rounded-md border border-zinc-300 bg-white px-2 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white";

  function emit(year: number, month: number, day: number) {
    const next = toIso(year, month, day);
    if (next !== value) onChange(next);
  }

  return (
    <div className="flex flex-wrap gap-2">
      <select
        aria-label="Gün"
        className={selectClass}
        disabled={disabled}
        value={Math.min(stamp.day, maxDay)}
        onChange={(event) => emit(stamp.year, stamp.month, Number(event.target.value))}
      >
        {Array.from({ length: maxDay }, (_, index) => index + 1).map((day) => (
          <option key={day} value={day}>
            {day}
          </option>
        ))}
      </select>
      <select
        aria-label="Ay"
        className={selectClass}
        disabled={disabled}
        value={stamp.month}
        onChange={(event) => emit(stamp.year, Number(event.target.value), stamp.day)}
      >
        {MONTHS_TR.map((label, index) => (
          <option key={label} value={index + 1}>
            {label}
          </option>
        ))}
      </select>
      <select
        aria-label="Yıl"
        className={selectClass}
        disabled={disabled}
        value={stamp.year}
        onChange={(event) => emit(Number(event.target.value), stamp.month, stamp.day)}
      >
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </div>
  );
}
