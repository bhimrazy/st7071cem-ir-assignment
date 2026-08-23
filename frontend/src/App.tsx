import { useCallback, useEffect, useState } from "react"
import NavHeader, { type TaskView } from "./components/NavHeader"
import ClusteringPage from "./pages/ClusteringPage"
import SearchPage from "./pages/SearchPage"

// Routing over the History API. App owns the path so both pages read the same
// value, rather than each calling pushState itself.
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
