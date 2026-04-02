import { createInvoice } from '../services/billing_service';
import { formatDate } from '../utils/date_utils';

export function InvoicePage(): any {
  const today = formatDate(new Date());
  return {
    render: () => `<div>Invoice - ${today}</div>`,
    generate: () => createInvoice(),
  };
}
