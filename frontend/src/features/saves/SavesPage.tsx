import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { Badge } from '../../components/ui/Badge'
import { useSavesQuery } from '../../hooks/useSavesQuery'
import type { SaveRecord } from '../../api/types'

type StatusFilter = 'all' | 'success' | 'pending' | 'failed'

function resolveStatus(save: SaveRecord): StatusFilter {
  if (save.status) {
    const lowered = save.status.toLowerCase()
    if (lowered.includes('pend')) return 'pending'
    if (lowered.includes('fail') || lowered.includes('error')) return 'failed'
    return 'success'
  }
  return save.success === 1 ? 'success' : 'failed'
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export default function SavesPage() {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [limit, setLimit] = useState(200)
  const {
    data: saves = [],
    isLoading,
    isError,
    refetch,
  } = useSavesQuery(limit)

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return saves.filter((item) => {
      const matchesSearch =
        !query ||
        item.id.toLowerCase().includes(query) ||
        item.url.toLowerCase().includes(query)
      const status = resolveStatus(item)
      const matchesStatus = statusFilter === 'all' || status === statusFilter
      return matchesSearch && matchesStatus
    })
  }, [saves, search, statusFilter])

  return (
    <section className="space-y-6">
      <header className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Saves</h1>
          <p className="text-sm text-slate-500">
            Browse and manage archived URLs fetched from the service.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select
            value={limit.toString()}
            onChange={(event) => setLimit(Number.parseInt(event.target.value, 10) || 200)}
            className="w-28"
          >
            {[50, 100, 200, 500].map((count) => (
              <option key={count} value={count}>
                Limit {count}
              </option>
            ))}
          </Select>
          <Button
            variant="secondary"
            onClick={() => {
              void refetch()
            }}
            disabled={isLoading}
          >
            Refresh
          </Button>
          <Button asChild>
            <Link to="/create">New Save</Link>
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader className="flex flex-col items-start gap-4 md:flex-row md:items-center md:justify-between">
          <CardTitle>Saves Table</CardTitle>
          <div className="flex w-full flex-col gap-3 md:w-auto md:flex-row">
            <Input
              placeholder="Search by URL or ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
            >
              <option value="all">All statuses</option>
              <option value="success">Success</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full table-fixed border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">URL</th>
                  <th className="px-3 py-2">Archiver</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Saved</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => {
                  const status = resolveStatus(item)
                  const badge =
                    status === 'success' ? (
                      <Badge variant="success">Success</Badge>
                    ) : status === 'pending' ? (
                      <Badge variant="warning">Pending</Badge>
                    ) : (
                      <Badge variant="danger">Failed</Badge>
                    )
                  const archiveTarget =
                    item.file_exists && item.relative_path
                      ? `/files/${item.relative_path}`
                      : item.url
                  return (
                    <tr key={item.rowid} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="px-3 py-3 font-medium text-slate-700">{item.id}</td>
                      <td className="px-3 py-3 text-slate-600 break-words">
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary-600 hover:underline"
                        >
                          {item.url}
                        </a>
                      </td>
                      <td className="px-3 py-3 text-slate-500">{item.archiver ?? '—'}</td>
                      <td className="px-3 py-3">{badge}</td>
                      <td className="px-3 py-3 text-slate-500">{formatDate(item.created_at)}</td>
                      <td className="px-3 py-3 text-right">
                        {archiveTarget ? (
                          <Button size="sm" variant="ghost" asChild>
                            <a href={archiveTarget} target="_blank" rel="noreferrer">
                              View
                            </a>
                          </Button>
                        ) : (
                          <span className="text-xs text-slate-400">No file</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {isLoading && <p className="py-6 text-center text-sm text-slate-500">Loading saves…</p>}
          {isError && (
            <p className="py-6 text-center text-sm text-danger">
              Failed to load saves. Please try refreshing.
            </p>
          )}
          {!isLoading && !isError && filtered.length === 0 && (
            <p className="py-6 text-center text-sm text-slate-500">No saves match this filter.</p>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
