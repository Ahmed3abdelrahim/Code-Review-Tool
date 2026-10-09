import { db } from "./db/client";
import { TaskRepository } from "./repositories/taskRepository";
import { TaskService } from "./services/taskService";

export const taskService = new TaskService(new TaskRepository(db));
