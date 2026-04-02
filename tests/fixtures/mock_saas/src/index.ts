import { handleCheckout } from './routes/checkout';
import { handleWebhook } from './routes/webhooks';

export function startServer(port: number): void {
  console.log(`Starting server on port ${port}`);
  handleCheckout();
  handleWebhook();
}

export const APP_VERSION = "1.0.0";
