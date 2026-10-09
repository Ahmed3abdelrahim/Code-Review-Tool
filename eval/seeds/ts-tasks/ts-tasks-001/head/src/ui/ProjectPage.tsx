import { taskService } from "../container";
import { TaskList } from "./TaskList";

interface ProjectPageProps {
  projectId: number;
}

export default async function ProjectPage({ projectId }: ProjectPageProps) {
  const tasks = await taskService.listTasks(projectId);
  return (
    <main>
      <h1>Project {projectId}</h1>
      <TaskList tasks={tasks} />
    </main>
  );
}
