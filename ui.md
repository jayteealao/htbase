# Frontend Redesign Plan

## Goals
- Deliver a modern, responsive web experience for the Archiver dashboard.
- Separate frontend from backend templates to enable independent deployment on a dedicated port.
- Improve UX for submitting saves, monitoring tasks, and interacting with ht preview tools.
- Establish a scalable component architecture (TypeScript + React) with consistent styling via modern CSS (Tailwind CSS or utility-first alternative).
- Ensure accessibility (WCAG AA alignment) and best practices (semantic HTML, keyboard support, reduced layout shifts).

## Target Stack
- **Framework**: React (via Vite + TypeScript) for fast dev server and production builds.
- **Styling**: Tailwind CSS with PostCSS + autoprefixer. Add a small design token layer for colors/spacing.
- **State/Data**: React Query (TanStack Query) for API fetching/caching; global store via Context where needed.
- **Routing**: React Router (for future multi-page flows, even if initial release is single-page).
- **UI Components**: Custom components + Headless UI or Radix primitives if needed.
- **Build Outputs**: Production assets served via static middleware on backend or separate host.
- **Dev Port**: Vite dev server on `http://localhost:5173` (configurable).

## Information Architecture
1. **Dashboard (landing page)**
   - Overview cards (total saves, queued tasks, last run, failures).
   - Recent activity timeline.
2. **Saves Management**
   - Filterable/searchable table of saves (status, archiver, timeframe).
   - Bulk actions (refresh, delete, export) roadmap.
   - Detail drawer/modal for individual save with metadata + actions.
3. **New Save Workflow**
   - Form with inline validation, archiver selection, and optional advanced options (skip duplicates, tags).
   - Success/error toasts and background task tracking.
4. **HT Console**
   - Live preview panel (iframe) and command sender, with history and better feedback.
5. **Settings (future)**
   - Config toggles, API keys, summarization controls.

## Visual Design Guidelines
- Adopt a light/dark theme toggle with base palette:
  - Primary: Indigo 600 (#4F46E5)
  - Secondary: Slate neutrals for backgrounds, accent with Emerald for success, Amber for warnings, Rose for errors.
- Typography: Inter font stack (web-safe fallback). Headings 600 weight, body 400.
- Spacing scale: multiples of 4px; container max width 1200px.
- Cards with subtle shadows, rounded corners (12px radius), consistent padding.
- Components use accessible color contrast (>4.5:1 body text, >3:1 UI elements).

## Component Architecture
- `src/components/` for shared primitives (Button, Input, Card, Table, Tag, Toast, Modal).
- `src/features/` scoped modules:
  - `saves/` (table, filters, detail views).
  - `create-save/` (form + validation).
  - `dashboard/` (metrics + timeline).
  - `ht-console/` (iframe + controls).
- `src/api/` for typed API clients (using OpenAPI or manual typing).
- Global layout components (`AppShell`, `Sidebar`, `Topbar`).
- Theming via Tailwind config and CSS variables.

## Data & Integration Plan
- Define base API client with axios or fetch wrapper supporting base URL configuration.
- Use React Query hooks (`useSaves`, `useCreateSave`, `useArchivers`, `useHtSend`, `useHtPreviewUrl`).
- Handle pagination (server returns limit/offset) and support infinite scroll or page controls.
- Websocket roadmap for live updates (future); initial version uses polling with stale time refresh.

## Accessibility & Performance
- Keyboard navigation for forms and tables (focus rings, skip links).
- ARIA roles for interactive widgets (modals, dialogs, toasts).
- Responsive breakpoints (mobile-first: 640px, 768px, 1024px, 1280px).
- Optimize bundle by code-splitting non-critical sections (HT console).
- Use Vite image optimization for icons/illustrations.

## Project Structure & Scripts
```
frontend/
  package.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    components/
    features/
    api/
    styles/
```
- npm scripts: `dev`, `build`, `preview`, `lint`, `format`.
- ESLint + Prettier with TypeScript config.
- PostCSS for Tailwind + autoprefixer.

## Step-by-Step Implementation
1. **Bootstrap Project**
   - `npm create vite@latest frontend -- --template react-ts`.
   - Install Tailwind CSS, React Router, React Query, axios, class-variance-authority (optional), heroicons.
   - Configure Tailwind (content paths, theme extensions), global CSS reset (`@tailwind base/components/utilities`).

2. **Set Up App Shell**
   - Create layout with sidebar (navigation) + top bar (search, user menu placeholder, theme toggle).
   - Implement router structure with lazy-loaded route components.
   - Implement global providers (React Query, Theme context).

3. **Build Core Features**
   - **Dashboard**: Cards showing aggregated stats (fetch from `/metrics` or derived from saves list) and activity timeline.
   - **Saves Table**: Data grid with sorting, filtering, status badges, pagination; row action menu.
   - **Create Save Form**: Form validation (React Hook Form + Zod), archiver dropdown, success toast.
   - **HT Console**: Panel with iframe that updates preview URL, command history, response messages.

4. **Enhance UX**
   - Add toasts (Radix/Headless) for operations.
   - Loading skeletons and empty states.
   - Confirmations via modal dialogs.

5. **Polish & Deploy**
   - Set up environment variables for API base URL.
   - Build static assets (`npm run build`) and expose via Nginx or FastAPI StaticFiles on new port.
   - Create Dockerfile (optional) or integrate with docker-compose (`frontend` service -> port 5173 dev / 4173 preview).
   - Document setup in README/UI docs.

## Hosting Strategy
- During development: run Vite dev server on `localhost:5173`, proxy API requests to backend 8000.
- Production: build static assets and serve via Nginx or `uvicorn` static mount on port 8080 (dedicated service in docker-compose).
- Update `docker-compose.yml` to add `frontend` service with Node 20 image for dev or a simple static server for production.

## Risks & Mitigations
- **API drift**: Define TypeScript types and centralize API clients.
- **Styling consistency**: Create Tailwind config tokens and enforce via lint rules.
- **Long lists**: Use virtualization (React Virtual) if dataset grows beyond manageable size.
- **Authentication**: Future-proof by designing layout to incorporate auth guards.

## Deliverables
- `frontend/` project with Vite React TS setup.
- Shared design tokens + Tailwind theme.
- Implemented Dashboard, Saves, Create Save, and HT Console views.
- Documentation (`README.frontend.md`) for setup and deployment.
