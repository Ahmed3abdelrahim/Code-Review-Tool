import { db } from "../db/client";
import type { TaskStatus } from "../domain/task";

interface StatusRow {
  status: TaskStatus;
  count: string;
}

const LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};

interface TaskSummaryProps {
  projectId: number;
}

export async function TaskSummary({ projectId }: TaskSummaryProps) {
  const rows = await db.query<StatusRow>(
    "SELECT status, count(*) AS count FROM tasks WHERE project_id = $1 AND NOT archived GROUP BY status",
    [projectId],
  );
  return (
    <dl className="task-summary">
      {rows.map((row) => (
        <div key={row.status}>
          <dt>{LABELS[row.status]}</dt>
          <dd>{Number(row.count)}</dd>
        </div>
      ))}
    </dl>
  );
}
