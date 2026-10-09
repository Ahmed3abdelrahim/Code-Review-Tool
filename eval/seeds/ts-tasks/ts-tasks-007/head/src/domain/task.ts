export type TaskStatus = "todo" | "in_progress" | "done";

export interface Task {
  id: number;
  projectId: number;
  title: string;
  status: TaskStatus;
  estimateHours: number;
  spentHours: number;
  dueDate: Date | null;
  createdAt: Date;
  completedAt: Date | null;
  archived: boolean;
}

export interface NewTaskInput {
  title: string;
  estimateHours: number;
  dueDate?: Date | null;
}
