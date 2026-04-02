import { processCharge, createInvoice } from '../services/billing_service';
import { CheckoutModal } from '../components/CheckoutModal';

export function handleCheckout(): void {
  const modal = CheckoutModal();
  processCharge();
  createInvoice();
}

export function validateCart(items: any[]): boolean {
  return items.length > 0;
}
