import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 p-6 text-center min-h-[60dvh]">
      <h1 className="text-gold font-bold">404</h1>
      <p className="text-text-secondary">Page not found</p>
      <Link
        to="/"
        className="inline-flex items-center justify-center px-6 py-3 rounded-lg border border-border text-text-primary hover:border-gold hover:text-gold transition-colors no-underline"
      >
        Back to Home
      </Link>
    </div>
  )
}
