import { useState, useCallback, useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Home, Library, Play, Settings, Menu, X, ChevronLeft, ChevronRight } from 'lucide-react'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import { cn } from '@/lib/utils'

/**
 * Navigation items used across all viewport sizes.
 * Each has a path, label, and lucide-react icon component.
 */
const navItems = [
  { path: '/', label: 'Home', icon: Home },
  { path: '/library', label: 'Library', icon: Library },
  { path: '/monitor', label: 'Monitor', icon: Play },
  { path: '/settings', label: 'Settings', icon: Settings },
] as const

/**
 * AppLayout — the main layout shell for AgentTown.
 *
 * Mobile (<640px): Top bar + bottom nav bar (sticky, thumb-zone).
 * Tablet (640-1024px): Top bar + overlay sidebar drawer (swipe/tap to dismiss).
 * Desktop (>1024px): Top bar + persistent collapsible sidebar.
 *
 * All interactive elements meet 44px minimum touch targets.
 */
export function AppLayout({ children }: { children: React.ReactNode }) {
  // Sidebar open state for tablet drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  // Desktop sidebar collapsed (icon-only) state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  // Track touch for swipe-to-dismiss on drawer overlay
  const touchStartX = useRef<number | null>(null)

  const location = useLocation()

  // Close drawer on route change
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  const toggleDrawer = useCallback(() => {
    setDrawerOpen(prev => !prev)
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
  }, [])

  // Swipe-to-dismiss: track touch start
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX
  }, [])

  // Swipe-to-dismiss: if user swipes left more than 80px, close the drawer
  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (touchStartX.current === null) return
    const deltaX = e.changedTouches[0].clientX - touchStartX.current
    if (deltaX < -80) {
      closeDrawer()
    }
    touchStartX.current = null
  }, [closeDrawer])

  return (
    <div className="min-h-dvh bg-bg-primary text-text-primary flex flex-col">
      {/* ===== TOP BAR ===== */}
      <header className="sticky top-0 z-50 flex items-center justify-between px-4 h-14 border-b border-border bg-bg-secondary">
        {/* Left: hamburger (tablet only) + title */}
        <div className="flex items-center gap-2">
          {/* Hamburger menu — visible on tablet (sm-lg), hidden on mobile (bottom nav) and desktop (persistent sidebar) */}
          <button
            onClick={toggleDrawer}
            className={cn(
              'hidden sm:flex lg:hidden',
              'items-center justify-center w-11 h-11 rounded-lg',
              'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
              'transition-colors',
            )}
            aria-label={drawerOpen ? 'Close navigation' : 'Open navigation'}
          >
            {drawerOpen ? <X size={22} /> : <Menu size={22} />}
          </button>

          <a
            href="/"
            className="text-gold font-bold text-lg no-underline hover:text-gold-bright transition-colors"
          >
            AgentTown
          </a>
        </div>

        {/* Right: connection status */}
        <ConnectionStatus />
      </header>

      {/* ===== BODY: sidebar (desktop/tablet) + main content ===== */}
      <div className="flex flex-1 overflow-hidden">
        {/* --- Desktop sidebar (>= 1024px): persistent, collapsible --- */}
        <aside
          className={cn(
            'hidden lg:flex flex-col',
            'border-r border-border bg-bg-secondary',
            'transition-[width] duration-200 ease-in-out',
            sidebarCollapsed ? 'w-16' : 'w-56',
          )}
        >
          <nav className="flex-1 flex flex-col gap-1 p-2 mt-2" role="navigation" aria-label="Main">
            {navItems.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg transition-colors',
                    'min-h-[44px] px-3',
                    sidebarCollapsed && 'justify-center px-0',
                    isActive
                      ? 'bg-gold/10 text-gold'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
                  )
                }
                title={sidebarCollapsed ? item.label : undefined}
              >
                <item.icon size={20} className="shrink-0" />
                {!sidebarCollapsed && <span className="text-sm font-medium">{item.label}</span>}
              </NavLink>
            ))}
          </nav>

          {/* Collapse/expand toggle at the bottom */}
          <button
            onClick={() => setSidebarCollapsed(prev => !prev)}
            className={cn(
              'flex items-center justify-center',
              'h-12 border-t border-border',
              'text-text-muted hover:text-text-secondary transition-colors',
            )}
            aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </aside>

        {/* --- Tablet drawer overlay (640-1024px) --- */}
        {drawerOpen && (
          <>
            {/* Overlay backdrop — tap to dismiss */}
            <div
              className="fixed inset-0 z-40 bg-black/50 sm:block lg:hidden"
              onClick={closeDrawer}
              onTouchStart={handleTouchStart}
              onTouchEnd={handleTouchEnd}
              aria-hidden="true"
            />
            {/* Drawer panel */}
            <aside
              className={cn(
                'fixed top-14 left-0 bottom-0 z-50 w-64',
                'bg-bg-secondary border-r border-border',
                'flex flex-col animate-gpu',
                'sm:block lg:hidden',
              )}
              style={{ animation: 'slideInLeft 200ms ease-out' }}
              onTouchStart={handleTouchStart}
              onTouchEnd={handleTouchEnd}
              role="navigation"
              aria-label="Main"
            >
              <nav className="flex-1 flex flex-col gap-1 p-3 mt-2">
                {navItems.map(item => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === '/'}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-3 rounded-lg px-4 transition-colors',
                        'min-h-[48px] text-base',
                        isActive
                          ? 'bg-gold/10 text-gold'
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary',
                      )
                    }
                  >
                    <item.icon size={20} className="shrink-0" />
                    <span className="font-medium">{item.label}</span>
                  </NavLink>
                ))}
              </nav>
            </aside>
          </>
        )}

        {/* --- Main content area --- */}
        <main className="flex-1 overflow-y-auto pb-16 sm:pb-0">
          {children}
        </main>
      </div>

      {/* ===== MOBILE BOTTOM NAV (< 640px) ===== */}
      {/* Sticky bottom bar in the thumb zone. 56px height, 44px+ touch targets. */}
      <nav
        className={cn(
          'fixed bottom-0 left-0 right-0 z-50 sm:hidden',
          'flex items-center justify-around',
          'h-14 bg-bg-secondary border-t border-border',
          'safe-area-pb',
        )}
        role="navigation"
        aria-label="Main"
      >
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              cn(
                'flex flex-col items-center justify-center gap-0.5',
                'min-w-[56px] min-h-[48px] px-2 rounded-lg',
                'transition-colors',
                isActive
                  ? 'text-gold'
                  : 'text-text-muted hover:text-text-secondary active:text-text-primary',
              )
            }
          >
            <item.icon size={22} />
            <span className="text-[10px] font-medium leading-tight">{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
