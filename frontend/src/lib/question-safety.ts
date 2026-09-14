/** Şık metninde cevap ipucu temizliği (LLM sızıntısı). */

const OPTION_LEAK_RE =
  /\s*[\(\[]?\s*(doğru|dogru|correct|cevap\s*[:\-]?|yan[iı]t\s*[:\-]?)\s*[\)\]]?/gi;

export function sanitizeOptionText(text: string): string {
  return String(text || "")
    .replace(OPTION_LEAK_RE, "")
    .replace(/\s*✓\s*/g, " ")
    .trim();
}

export function sanitizeOptions(options: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(options || {}).map(([letter, text]) => [
      letter,
      sanitizeOptionText(text),
    ]),
  );
}
