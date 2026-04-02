import { formatDate } from './date_utils';

export function formatCurrency(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

export function formatPercentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDateTime(date: Date): string {
  return `${formatDate(date)} ${date.toTimeString().split(' ')[0]}`;
}
