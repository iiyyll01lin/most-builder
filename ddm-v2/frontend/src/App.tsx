import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from '@/store/authStore'
import { LoginPage } from '@/pages/LoginPage'
import { ProjectDashboard } from '@/pages/ProjectDashboard'
import { FactoryManagerDashboard } from '@/pages/FactoryManagerDashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Minimal project selector — replace with a proper router (react-router) when scaling.
function ProjectSelector({ onSelect }: { onSelect: (id: string) => void }) {
  const [value, setValue] = useState('')
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0e1a]">
      <div className="space-y-4 rounded-2xl border border-gray-700 bg-gray-900 p-8 w-full max-w-sm">
        <h2 className="text-lg font-bold text-gray-100">Open Project</h2>
        <input
          autoFocus
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Project ID (e.g. proj-001)"
          className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-cyan-500 focus:outline-none"
          onKeyDown={(e) => e.key === 'Enter' && value.trim() && onSelect(value.trim())}
        />
        <button
          onClick={() => value.trim() && onSelect(value.trim())}
          disabled={!value.trim()}
          className="w-full rounded-lg bg-cyan-600 py-2 text-sm font-medium text-white hover:bg-cyan-500 transition-colors disabled:opacity-60"
        >
          Load Dashboard
        </button>
      </div>
    </div>
  )
}

type ActiveView = 'project' | 'bi'

function AppShell() {
  const token = useAuthStore((s) => s.token)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const user = useAuthStore((s) => s.user)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [activeView, setActiveView] = useState<ActiveView>('project')

  if (!token) return <LoginPage />
  if (!projectId) return <ProjectSelector onSelect={setProjectId} />

  return (
    <div className="min-h-screen bg-[#0a0e1a]">
      {/* Top nav */}
      <nav className="sticky top-0 z-50 flex items-center justify-between border-b border-gray-800 bg-gray-900/80 px-6 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setProjectId(null)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            ← Projects
          </button>
          <span className="text-gray-700">|</span>
          <span className="text-sm font-semibold text-cyan-400">DDM IE/PE Console</span>
          <span className="text-gray-700">|</span>
          {/* View switcher */}
          <button
            onClick={() => setActiveView('project')}
            className={`text-xs px-2 py-0.5 rounded transition-colors ${
              activeView === 'project'
                ? 'bg-cyan-800/50 text-cyan-300'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            SOP Workspace
          </button>
          <button
            onClick={() => setActiveView('bi')}
            className={`text-xs px-2 py-0.5 rounded transition-colors ${
              activeView === 'bi'
                ? 'bg-cyan-800/50 text-cyan-300'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Factory Manager AI
          </button>
        </div>
        <button
          onClick={clearAuth}
          className="text-xs text-gray-500 hover:text-red-400 transition-colors"
        >
          Sign out {user?.name ? `(${user.name})` : ''}
        </button>
      </nav>

      <main>
        {activeView === 'project' && <ProjectDashboard projectId={projectId} />}
        {activeView === 'bi' && <FactoryManagerDashboard />}
      </main>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1f2937',
            color: '#f9fafb',
            border: '1px solid #374151',
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: '13px',
          },
          error: {
            style: {
              border: '1px solid #7f1d1d',
              background: '#1c0a0a',
              color: '#f87171',
            },
            duration: 6000,
          },
          success: {
            style: {
              border: '1px solid #064e3b',
              background: '#0a1c17',
              color: '#34d399',
            },
          },
        }}
      />
    </QueryClientProvider>
  )
}
