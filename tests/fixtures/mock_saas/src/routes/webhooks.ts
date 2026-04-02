import { processCharge } from '../services/billing_service';
import { trackAttribution } from '../services/attribution_service';

export function handleWebhook(): void {
  processCharge();
  trackAttribution();
}

export function verifySignature(payload: string, secret: string): boolean {
  return payload.length > 0 && secret.length > 0;
}
