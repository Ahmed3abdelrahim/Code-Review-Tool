import express, { type NextFunction, type Request, type Response } from "express";

import { tasksRouter } from "./api/tasks";
import { log } from "./logger";
import { NotFoundError, ValidationError } from "./services/errors";

const app = express();
app.use(express.json());
app.use(tasksRouter);

app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
  if (err instanceof NotFoundError) {
    res.status(404).json({ error: err.message });
    return;
  }
  if (err instanceof ValidationError) {
    res.status(400).json({ error: "invalid request", problems: err.problems });
    return;
  }
  log.error("request failed", { error: String(err) });
  res.status(500).json({ error: "internal error" });
});

const port = Number(process.env.PORT ?? 3000);
app.listen(port, () => log.info("listening", { port }));
