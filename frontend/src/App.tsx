import { useCallback, useEffect, useState } from "react"
import NavHeader, { type TaskView } from "./components/NavHeader"
import ClusteringPage from "./pages/ClusteringPage"
import SearchPage from "./pages/SearchPage"

/**
 * Routing over the History API, without a router library.
 *
 * Three shapes: `/` (with an optional `?q=`), `/author/<name>` and
 * `/clustering`. Real URLs matter here even at this size: an author page and
 * the clustering page should both be bookmarkable and reachable with the back
 * button, which a view toggled by component state is not.
 *
 * App owns the current path so both pages read the same value, and passes
 * `navigate` down instead of letting pages call pushState themselves. FastAPI
 * serves index.html for unmatched HTML routes, so deep links load on a cold
 * request rather than 404ing.
 */
function currentPath(): string {
  return window.location.pathname + window.location.search
}

function viewFor(path: string): TaskView {
  return path.startsWith("/clustering") ? "clustering" : "search"
}

export default function App() {
  const [path, setPath] = useState(currentPath)

  useEffect(() => {
    const onPopState = () => setPath(currentPath())
    window.addEventListener("popstate", onPopState)
    return () => window.removeEventListener("popstate", onPopState)
  }, [])

  const navigate = useCallback((to: string) => {
    if (to === currentPath()) return
    window.history.pushState({}, "", to)
    setPath(to)
  }, [])

  const view = viewFor(path)

  useEffect(() => {
    document.title =
      view === "clustering"
        ? "Document Clustering"
        : "CHCT Publication Search"
  }, [view])

  return (
    <>
      <NavHeader
        active={view}
        onNavigate={(next) => navigate(next === "clustering" ? "/clustering" : "/")}
      />
      {view === "clustering" ? (
        <ClusteringPage />
      ) : (
        <SearchPage path={path} navigate={navigate} />
      )}
    </>
  )
}
