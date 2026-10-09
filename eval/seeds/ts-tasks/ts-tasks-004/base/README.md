# tasks

Task tracking for small teams: projects, tasks, time logging.

## Layout

- `src/api` - Express routes
- `src/ui` - server-rendered React pages and components
- `src/services` - business logic
- `src/repositories` - data access
- `src/db` - PostgreSQL client
- `src/domain` - domain types
- `src/container.ts` - wires repositories into services

Routes and pages use services only, through `src/container.ts`.

## Development

    npm ci
    npm test
    DATABASE_URL=postgres://localhost/tasks npm run dev
