import { formatDate } from '../utils/date_utils';
import { runQuery } from '../db/queries';

export function processCharge(): void {
  const date = formatDate(new Date());
  runQuery(`INSERT INTO charges (date) VALUES ('${date}')`);
}

export function createInvoice(): void {
  const date = formatDate(new Date());
  runQuery(`INSERT INTO invoices (date) VALUES ('${date}')`);
}

export function refund(chargeId: string): void {
  runQuery(`UPDATE charges SET refunded = true WHERE id = '${chargeId}'`);
}
