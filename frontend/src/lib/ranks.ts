export const RANK_ACEMI = "Acemi Tilki";
export const RANK_KURNAZ = "Kurnaz Prens";
export const RANK_KIDEMLI = "Kıdemli Tilki";
export const RANK_ALFA = "Alfa Tilki";
export const RANK_EMOJI = "🦊";

export function foxRank(xp: number | null | undefined): {
  title: string;
  emoji: string;
} {
  const value = Math.max(Math.floor(xp || 0), 0);
  if (value >= 3000) return { title: RANK_ALFA, emoji: RANK_EMOJI };
  if (value >= 1500) return { title: RANK_KIDEMLI, emoji: RANK_EMOJI };
  if (value >= 500) return { title: RANK_KURNAZ, emoji: RANK_EMOJI };
  return { title: RANK_ACEMI, emoji: RANK_EMOJI };
}

export function address(xp: number | null | undefined): string {
  return foxRank(xp).title;
}
