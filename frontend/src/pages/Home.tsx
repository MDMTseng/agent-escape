import { Link } from 'react-router-dom'

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center gap-6 p-6 text-center min-h-[60dvh]">
      <h1 className="text-gold font-bold tracking-tight">AgentTown</h1>
      <p className="text-text-secondary max-w-md">
        A virtual world where LLM-powered agents live, interact, and solve escape rooms together.
      </p>
      <div className="flex flex-col sm:flex-row gap-3 mt-4">
        <Link
          to="/library"
          className="inline-flex items-center justify-center px-6 py-3 rounded-lg bg-gold text-bg-primary font-semibold hover:bg-gold-bright transition-colors no-underline"
        >
          Scene Library
        </Link>
        <Link
          to="/monitor"
          className="inline-flex items-center justify-center px-6 py-3 rounded-lg border border-border text-text-primary hover:border-gold hover:text-gold transition-colors no-underline"
        >
          Game Monitor
        </Link>
      </div>
    </div>
  )
}
