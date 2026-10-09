import { Router } from "express";

import { taskService } from "../container";

export const tasksRouter = Router();

tasksRouter.get("/projects/:projectId/tasks", async (req, res, next) => {
  try {
    res.json(await taskService.listTasks(Number(req.params.projectId)));
  } catch (err) {
    next(err);
  }
});

tasksRouter.post("/projects/:projectId/tasks", async (req, res, next) => {
  try {
    const task = await taskService.createTask(Number(req.params.projectId), req.body);
    res.status(201).json(task);
  } catch (err) {
    next(err);
  }
});

tasksRouter.get("/tasks/:id", async (req, res, next) => {
  try {
    res.json(await taskService.getTask(Number(req.params.id)));
  } catch (err) {
    next(err);
  }
});

tasksRouter.post("/tasks/:id/complete", async (req, res, next) => {
  try {
    res.json(await taskService.completeTask(Number(req.params.id)));
  } catch (err) {
    next(err);
  }
});

tasksRouter.post("/tasks/:id/time", async (req, res, next) => {
  try {
    res.json(await taskService.logTime(Number(req.params.id), Number(req.body.hours)));
  } catch (err) {
    next(err);
  }
});
