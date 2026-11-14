# Agent Directives: Git, Quality, Testing & Planning Standards

## 1. Git Workflow & Branching
- NEVER push directly to the `main` branch.
- All development, feature work, and routine commits MUST occur on `develop` (or feature branches derived from `develop`).
- Changes can ONLY be promoted to `main` via a Pull Request (PR) targeted from `develop`, keeping `develop` and `main` aligned in structure.
- **Development Tooling Organization & HACS Isolation:** Keep and track internal development tools, test suites, and sandbox configurations in `.dev-tools/`. Since HACS only downloads and installs `custom_components/smart_zone_heating/` onto user instances, `.dev-tools/` can safely live on both `develop` and `main`, while `custom_components/smart_zone_heating/` must contain strictly production integration files (never place test or dev files inside `custom_components/`).

## 2. Tag Management
- NEVER delete, overwrite, or force-push (`git push --force`) existing Git tags unless explicitly instructed by the user.
- If a new tag is required and no specific version is specified, create a new incremental tag following Semantic Versioning (SemVer).

## 3. Pre-PR Quality Gates
- Before opening any Pull Request targeting `main`, you MUST run all existing code quality checks (linter, code formatter, unit/integration tests, and static analysis).
- If code quality tools or linters are NOT configured in the repository, DO NOT open the PR. Stop and ask the user how they would like them set up.

## 4. Code Quality & Static Analysis
- Adhere strictly to Clean Code and Sonar/SonarLint best practices:
  - Keep cyclomatic and cognitive complexity low; keep functions small and single-purpose.
  - Zero dead code, unused imports, or duplicate logic.
  - Strict null/undefined handling and defensive programming. Never silence exceptions with empty catch blocks.
- Security: NEVER hardcode secrets, credentials, tokens, or private keys. Always use environment variables or secret providers.
- Maintain existing code style. Do not reformat untouched sections of files.

## 5. Local Sandbox, Testing & Testcontainers Policy
- **Local Development Sandbox:** Conduct local development, execution, and debugging inside isolated container environments (using Testcontainers or dedicated development containers) to avoid polluting the host machine's environment and to provide the agent with a clean, reproducible sandbox.
- Accompany every bugfix or feature with comprehensive automated tests.
- For integration testing involving external dependencies (e.g., relational databases, NoSQL, message brokers, Redis, object storage), ALWAYS prefer **Testcontainers** over in-memory substitutes (e.g., H2) or manual mocks.
- Ensure Testcontainers configurations:
  - Use dynamic/randomized port bindings to prevent port conflicts in parallel test runs and CI environments.
  - Clean up resources properly after execution (rely on test lifecycle hooks or Ryuk).
  - Use explicit, pinned version tags for container images (NEVER use `latest`).
- If a local Docker daemon is unavailable or cannot run containers, pause and ask the user before falling back to mocks or stubs.

## 6. Planning, Confirmation & Task Tracking
- **Plan Confirmation for Complex Changes:** Before executing complex refactoring, multi-file changes, or architectural shifts, DO NOT jump straight into writing code. Present a clear, concise plan or visual outline (flowchart, sequence, or file impact tree) and explicitly ask for user confirmation first.
- **Task Deconstruction & Prioritization:** When requested to implement multiple features, fixes, or broad requirements at once:
  1. Break the request down into distinct, logical subtasks.
  2. Propose a sensible roadmap/priority order and ask the user which item to tackle first.
  3. Wait for direction before implementing the remaining items.
- **Tracking File (`.dev-tools/TASK_PROGRESS.md`):** Always create or update a dedicated tracking file in `.dev-tools/TASK_PROGRESS.md` to record:
  - Currently in-progress items.
  - Completed items and architectural decisions made.
  - Backlog/pending tasks waiting for future implementation.
