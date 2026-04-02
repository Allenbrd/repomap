import { runQuery } from '../db/queries';

export function getUser(userId: string): any {
  return runQuery(`SELECT * FROM users WHERE id = '${userId}'`);
}

export function updateUser(userId: string, data: any): void {
  runQuery(`UPDATE users SET data = '${JSON.stringify(data)}' WHERE id = '${userId}'`);
}
