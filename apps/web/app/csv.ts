export type CsvCell = string | number | null | undefined;

function escapeCsvCell(value: CsvCell) {
  if (value === null || value === undefined) return '';

  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function createCsv(rows: CsvCell[][]) {
  return rows.map((row) => row.map(escapeCsvCell).join(',')).join('\r\n');
}

export function safeCsvFilenamePart(value: string) {
  return value.trim().replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_') || 'club';
}

export function downloadCsv(filename: string, rows: CsvCell[][]) {
  const blob = new Blob(['\uFEFF', createCsv(rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();

  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
