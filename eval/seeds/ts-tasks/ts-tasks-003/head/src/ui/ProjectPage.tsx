import { taskService } from "../container";
import { removeCompleted } from "./filters";
import { TaskList } from "./TaskList";

interface ProjectPageProps {
  projectId: number;
  hideCompleted?: boolean;
}

export default async function ProjectPage({ projectId, hideCompleted = false }: ProjectPageProps) {
  const tasks = await taskService.listTasks(projectId);
  const visible = hideCompleted ? removeCompleted(tasks) : tasks;
  return (
    <main>
      <h1>Project {projectId}</h1>
      <a href={`?hideCompleted=${!hideCompleted}`}>
        {hideCompleted ? "Show completed tasks" : "Hide completed tasks"}
      </a>
      <TaskList tasks={visible} />
    </main>
  );
}
