import { taskService } from "../container";
import { TaskList } from "./TaskList";
import { TaskSummary } from "./TaskSummary";

interface ProjectPageProps {
  projectId: number;
}

export default async function ProjectPage({ projectId }: ProjectPageProps) {
  const tasks = await taskService.listTasks(projectId);
  return (
    <main>
      <h1>Project {projectId}</h1>
      <TaskSummary projectId={projectId} />
      <TaskList tasks={tasks} />
    </main>
  );
}
