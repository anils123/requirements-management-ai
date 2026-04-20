import { Sidebar } from './components/Sidebar'
import { ChatPage } from './pages/ChatPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { RequirementsPage } from './pages/RequirementsPage'
import { ExpertsPage } from './pages/ExpertsPage'
import { WorkspacesPage } from './pages/WorkspacesPage'
import { AdminPage } from './pages/AdminPage'
import { useStore } from './store'

const PAGES: Record<string, React.ComponentType> = {
  chat:         ChatPage,
  documents:    DocumentsPage,
  requirements: RequirementsPage,
  experts:      ExpertsPage,
  workspaces:   WorkspacesPage,
  admin:        AdminPage,
}

export default function App() {
  const { activeTab } = useStore()
  const Page = PAGES[activeTab] || ChatPage

  return (
    <div className="flex h-screen overflow-hidden bg-surface-900">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        <Page />
      </main>
    </div>
  )
}
