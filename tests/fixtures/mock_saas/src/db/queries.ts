export function runQuery(sql: string): any {
  console.log(`Executing query: ${sql}`);
  return { rows: [] };
}

export function transaction(queries: string[]): void {
  queries.forEach(q => runQuery(q));
}
