import { useMemo } from 'react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card'
import { useSavesQuery } from '../../hooks/useSavesQuery'
import type { SaveRecord } from '../../api/types'

function resolveStatus(save: SaveRecord): 'success' | 'pending' | 'failed' {
  if (save.status) {
    const lowered = save.status.toLowerCase()
    if (lowered.includes('pend')) {
      return 'pending'
    }
    if (lowered.includes('fail') || lowered.includes('error')) {
      return 'failed'
    }
    return 'success'
  }
  return save.success === 1 ? 'success' : 'failed'
}

function formatDate(date: Date | null) {
  if (!date || Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatRelative(date: Date | null) {
  if (!date || Number.isNaN(date.getTime())) return 'Unknown'
  const diffMs = Date.now() - date.getTime()
  const diffMinutes = Math.round(diffMs / 60000)
  if (diffMinutes < 1) return 'moments ago'
  if (diffMinutes < 60) return `${diffMinutes} min ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return diffDays === 1 ? '1 day ago' : `${diffDays} days ago`
}

export default function DashboardPage() {
  const {
    data: saves = [],
    isLoading,
    isError,
    refetch,
  } = useSavesQuery(200)

  const metrics = useMemo(() => {
    if (!saves.length) {
      return [
        { label: 'Total Saves', value: isLoading ? '…' : '0', subtitle: 'Past 24h: 0' },
        { label: 'Pending Tasks', value: '0', subtitle: 'Queue length' },
        { label: 'Failed Runs', value: '0', subtitle: 'Last 7 days' },
        { label: 'Last Execution', value: '—', subtitle: 'UTC' },
      ]
    }

    const now = Date.now()
    const total = saves.length
    const pending = saves.filter((save) => resolveStatus(save) === 'pending').length
    const failed = saves.filter((save) => resolveStatus(save) === 'failed').length
    const last24h = saves.filter((save) => {
      if (!save.created_at) return false
      const created = new Date(save.created_at)
      if (Number.isNaN(created.getTime())) return false
      return now - created.getTime() <= 86_400_000
    }).length

    const lastDate = saves
      .map((save) => (save.created_at ? new Date(save.created_at) : null))
      .filter((d): d is Date => Boolean(d && !Number.isNaN(d.getTime())))
      .sort((a, b) => b.getTime() - a.getTime())[0] ?? null

    return [
      {
        label: 'Total Saves',
        value: total.toString(),
        subtitle: `Past 24h: ${last24h}`,
      },
      {
        label: 'Pending Tasks',
        value: pending.toString(),
        subtitle: 'Queue length',
      },
      {
        label: 'Failed Runs',
        value: failed.toString(),
        subtitle: 'Last 7 days (from fetch)',
      },
      {
        label: 'Last Execution',
        value: formatDate(lastDate),
        subtitle: 'UTC',
      },
    ]
  }, [isLoading, saves])

  const timeline = useMemo(() => {
    const sorted = [...saves].sort((a, b) => {
      const aDate = a.created_at ? new Date(a.created_at).getTime() : 0
      const bDate = b.created_at ? new Date(b.created_at).getTime() : 0
      return bDate - aDate
    })
    return sorted.slice(0, 6).map((save) => {
      const created = save.created_at ? new Date(save.created_at) : null
      return {
        title: save.url,
        status: resolveStatus(save),
        time: formatRelative(created),
        created,
        id: save.rowid,
      }
    })
  }, [saves])

  return (
    <section className="space-y-8">
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <Card key={metric.label} className="bg-gradient-to-br from-white to-slate-50">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary-500">
              {metric.label}
            </p>
            <p className="mt-4 text-4xl font-semibold tracking-tight text-slate-900">
              {metric.value}
            </p>
            <p className="mt-2 text-xs text-slate-500">{metric.subtitle}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <Card>
          <CardHeader className="flex items-center justify-between">
            <CardTitle>Recent Activity</CardTitle>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                void refetch()
              }}
            >
              Refresh
            </Button>
          </CardHeader>
          <CardContent className="space-y-6">
            {isError && (
              <p className="text-sm text-danger">Unable to load activity. Try refreshing.</p>
            )}
            {isLoading && !saves.length && <p className="text-sm text-slate-500">Loading saves…</p>}
            {timeline.map((item) => (
              <div key={item.id} className="flex items-start gap-4">
                <div className="mt-1 h-2 w-2 rounded-full bg-primary-500" />
                <div>
                  <p className="text-sm font-medium text-slate-700 break-words">
                    {item.title}
                  </p>
                  <div className="mt-1 flex items-center gap-3 text-xs text-slate-400">
                    <span>{item.time}</span>
                    <Badge
                      variant={
                        item.status === 'success'
                          ? 'success'
                          : item.status === 'pending'
                            ? 'warning'
                            : 'danger'
                      }
                    >
                      {item.status}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
            {!timeline.length && !isLoading && !isError && (
              <p className="text-sm text-slate-500">No recent activity yet.</p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm">
                <Button asChild variant="secondary" className="w-full justify-start">
                  <a href="/create">Queue new save</a>
                </Button>
                <Button asChild variant="secondary" className="w-full justify-start">
                  <a href="/saves">View saves</a>
                </Button>
                <Button asChild variant="secondary" className="w-full justify-start">
                  <a href="/ht-console">Open ht console</a>
                </Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>System Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-500">
              <p>
                Archiver service: <Badge variant="success">Healthy</Badge>
              </p>
              <p>
                Summarizer queue: <Badge variant="warning">Idle</Badge>
              </p>
              <p>
                ht runner: <Badge variant="success">Online</Badge>
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  )
}
