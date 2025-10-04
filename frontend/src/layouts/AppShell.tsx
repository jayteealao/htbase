import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { cn } from '../lib/cn'

type NavItem = {
  label: string
  to: string
  description: string
}

const navItems: NavItem[] = [
  { label: 'Dashboard', to: '/', description: 'Overview and key metrics' },
  { label: 'Saves', to: '/saves', description: 'Search and manage saved URLs' },
  { label: 'Create Save', to: '/create', description: 'Submit new items to archive' },
  { label: 'HT Console', to: '/ht-console', description: 'Live preview and command sender' },
]

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="relative flex min-h-screen bg-slate-100 text-slate-900">
      {/* Sidebar */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-72 border-r border-slate-200 bg-white px-6 py-8 transition-transform duration-200 ease-in-out lg:static lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-primary-500">
              Archiver
            </p>
            <h1 className="mt-1 text-xl font-bold tracking-tight">Control Center</h1>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="lg:hidden"
            onClick={() => setSidebarOpen(false)}
          >
            Close
          </Button>
        </div>

        <nav className="mt-10 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'block rounded-xl px-4 py-3 transition hover:bg-slate-100',
                  isActive ? 'bg-primary-50 text-primary-700' : 'text-slate-600',
                )
              }
              onClick={() => setSidebarOpen(false)}
            >
              <p className="text-sm font-semibold">{item.label}</p>
              <p className="text-xs text-slate-500">{item.description}</p>
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto hidden pt-12 text-xs text-slate-400 lg:block">
          <p>Build {new Date().toISOString().split('T')[0]}</p>
          <p>Serving on port 5173</p>
        </div>
      </div>

      {/* Content */}
      <div className="flex flex-1 flex-col lg:pl-72">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white/90 px-6 py-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setSidebarOpen((prev) => !prev)}
            >
              Menu
            </Button>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Archiver Dashboard</h2>
              <p className="text-xs text-slate-500">Monitor saves, trigger runs, inspect results.</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button asChild size="sm" variant="secondary">
              <a href="/docs" target="_blank" rel="noreferrer">
                API Docs
              </a>
            </Button>
            <Button size="sm" variant="secondary">
              Theme
            </Button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-6 py-10">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
