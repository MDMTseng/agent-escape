import { Routes, Route } from 'react-router-dom'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import Home from '@/pages/Home'
import Library from '@/pages/Library'
import Monitor from '@/pages/Monitor'
import NotFound from '@/pages/NotFound'

function App() {
  return (
    <div className="min-h-dvh bg-bg-primary text-text-primary flex flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-bg-secondary">
        <a href="/" className="text-gold font-bold text-lg no-underline hover:text-gold-bright transition-colors">
          AgentTown
        </a>
        <ConnectionStatus />
      </header>

      {/* Main content */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/library" element={<Library />} />
          <Route path="/monitor" element={<Monitor />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>

      {/* Bottom bar - thumb zone for mobile primary actions (future use) */}
      <footer className="px-4 py-2 border-t border-border bg-bg-secondary text-center text-text-muted text-xs">
        AgentTown Escape Room
      </footer>
    </div>
  )
}

export default App
