# Frontend

React, TypeScript and Tailwind. One interface for both tasks, switched by the
nav bar: `/` for the search engine, `/clustering` for document clustering.

```bash
npm install
npm run dev     # localhost:5173, proxies /api to the backend on :8000
npm run build   # writes dist/, which FastAPI then serves itself
```

```
src/
  pages/       SearchPage, ClusteringPage
  components/  shared UI, including hand-rolled SVG charts
  api.ts       every call to the backend
  types.ts     mirrors backend/src/api/models.py
```

Routing is done with the History API directly rather than a router library,
since there are only three routes.
