import type { Task } from "../domain/task";
import { progress } from "../services/progress";

interface TaskListProps {
  tasks: Task[];
}

export function TaskList({ tasks }: TaskListProps) {
  if (tasks.length === 0) {
    return <p className="empty">No tasks yet.</p>;
  }
  return (
    <ul className="task-list">
      {tasks.map((task) => (
        <li key={task.id} className={`task task--${task.status}`}>
          <span className="task__title">{task.title}</span>
          <progress value={progress(task)} max={1} />
        </li>
      ))}
    </ul>
  );
}
