import { processCharge } from '../services/billing_service';

export function CheckoutModal(): any {
  return {
    render: () => '<div>Checkout</div>',
    onSubmit: () => processCharge(),
  };
}

export function CheckoutButton(): any {
  return { render: () => '<button>Pay Now</button>' };
}
