import { formatPercentage } from '../utils/format_helpers';
import { runQuery } from '../db/queries';

export function trackAttribution(): void {
  const rate = formatPercentage(0.15);
  runQuery(`INSERT INTO attributions (rate) VALUES ('${rate}')`);
}

export function getAttributionReport(): any {
  return runQuery('SELECT * FROM attributions');
}
