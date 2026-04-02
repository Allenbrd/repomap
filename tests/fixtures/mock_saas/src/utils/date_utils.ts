export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export function parseISO(dateStr: string): Date {
  return new Date(dateStr);
}

export function daysBetween(start: Date, end: Date): number {
  const diff = end.getTime() - start.getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}
