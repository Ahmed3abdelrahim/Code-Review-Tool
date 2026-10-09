import type { DbClient } from "../db/client";
import type { NewTaskInput, Task, TaskStatus } from "../domain/task";

interface TaskRow {
  id: number;
  project_id: number;
  title: string;
  status: TaskStatus;
  estimate_hours: string;
  spent_hours: string;
  due_date: Date | null;
  created_at: Date;
  completed_at: Date | null;
  archived: boolean;
}

const COLUMNS =
  "id, project_id, title, status, estimate_hours, spent_hours, due_date, created_at, completed_at, archived";

function toTask(row: TaskRow): Task {
  return {
    id: row.id,
    projectId: row.project_id,
    title: row.title,
    status: row.status,
    estimateHours: Number(row.estimate_hours),
    spentHours: Number(row.spent_hours),
    dueDate: row.due_date,
    createdAt: row.created_at,
    completedAt: row.completed_at,
    archived: row.archived,
  };
}

export interface TaskStore {
  findById(id: number): Promise<Task | null>;
  listByProject(projectId: number): Promise<Task[]>;
  insert(projectId: number, input: NewTaskInput): Promise<Task>;
  save(task: Task): Promise<void>;
}

export class TaskRepository implements TaskStore {
  constructor(private readonly db: DbClient) {}

  async findById(id: number): Promise<Task | null> {
    const rows = await this.db.query<TaskRow>(`SELECT ${COLUMNS} FROM tasks WHERE id = $1`, [id]);
    return rows[0] ? toTask(rows[0]) : null;
  }

  async listByProject(projectId: number): Promise<Task[]> {
    const rows = await this.db.query<TaskRow>(
      `SELECT ${COLUMNS} FROM tasks WHERE project_id = $1 AND NOT archived ORDER BY created_at, id`,
      [projectId],
    );
    return rows.map(toTask);
  }

  async insert(projectId: number, input: NewTaskInput): Promise<Task> {
    const rows = await this.db.query<TaskRow>(
      `INSERT INTO tasks (project_id, title, estimate_hours, due_date)
       VALUES ($1, $2, $3, $4)
       RETURNING ${COLUMNS}`,
      [projectId, input.title, input.estimateHours, input.dueDate ?? null],
    );
    if (!rows[0]) {
      throw new Error("insert returned no row");
    }
    return toTask(rows[0]);
  }

  async save(task: Task): Promise<void> {
    await this.db.query(
      `UPDATE tasks
       SET title = $2, status = $3, estimate_hours = $4, spent_hours = $5,
           due_date = $6, completed_at = $7, archived = $8
       WHERE id = $1`,
      [
        task.id,
        task.title,
        task.status,
        task.estimateHours,
        task.spentHours,
        task.dueDate,
        task.completedAt,
        task.archived,
      ],
    );
  }
}
