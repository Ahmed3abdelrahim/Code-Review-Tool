import pg from "pg";

export interface DbClient {
  query<T>(sql: string, params?: unknown[]): Promise<T[]>;
}

const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });

export const db: DbClient = {
  async query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
    const result = await pool.query(sql, params);
    return result.rows as T[];
  },
};
