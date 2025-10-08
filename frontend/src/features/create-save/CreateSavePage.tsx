import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'

import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { Label } from '../../components/ui/Label'
import { Select } from '../../components/ui/Select'
import { runArchiver } from '../../api/saves'
import { useArchiversQuery } from '../../hooks/useArchivers'
import type { SaveResponse, TaskAccepted } from '../../api/types'

const schema = z.object({
  url: z.string().url({ message: 'Use a valid URL including protocol.' }),
  id: z
    .string()
    .min(1, { message: 'Provide an item identifier.' })
    .max(120, { message: 'Keep IDs under 120 characters.' }),
  archiver: z.string().min(1, { message: 'Select an archiver.' }),
})

type FormValues = z.infer<typeof schema>

export default function CreateSavePage() {
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const {
    data: archivers = [],
    isLoading: archiversLoading,
    isError: archiversError,
  } = useArchiversQuery()

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
    watch,
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      url: '',
      id: '',
      archiver: 'all',
    },
  })

  useEffect(() => {
    if (!archiversLoading && !archiversError && archivers.length) {
      reset((prev) => ({ ...prev, archiver: prev.archiver || 'all' }))
    }
  }, [archivers, archiversError, archiversLoading, reset])

  const availableArchivers = useMemo(() => {
    const list = archivers.length ? archivers : []
    return ['all', ...list]
  }, [archivers])

  const mutation = useMutation({
    mutationFn: (payload: FormValues) => runArchiver(payload),
    onSuccess: (result, variables) => {
      setError(null)
      if (isTaskAccepted(result)) {
        setMessage(`Task queued (${result.task_id}) for ${variables.id}.`)
      } else {
        const info = result.ok
          ? `Archiver completed${result.saved_path ? ` (${result.saved_path})` : ''}`
          : `Archiver failed${result.exit_code ? ` (exit ${result.exit_code})` : ''}`
        setMessage(info)
      }
      reset({ url: '', id: '', archiver: variables.archiver })
    },
    onError: (err: unknown) => {
      setMessage(null)
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Failed to queue save. Please try again.')
      }
    },
  })

  const onSubmit = handleSubmit(async (values) => {
    setMessage(null)
    setError(null)
    await mutation.mutateAsync(values)
  })

  const submitting = isSubmitting || mutation.isPending
  const selectedArchiver = watch('archiver')

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Create Save</h1>
        <p className="text-sm text-slate-500">
          Submit a new URL to the archiver pipeline. Choose a specific archiver or use the
          multi-step <strong>all</strong> workflow.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Save Parameters</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-6"
            onSubmit={(event) => {
              void onSubmit(event)
            }}
            noValidate
          >
            <div className="space-y-2">
              <Label htmlFor="url">URL</Label>
              <Input id="url" placeholder="https://example.com" {...register('url')} />
              {errors.url && <p className="text-sm text-danger">{errors.url.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="id">Item ID</Label>
              <Input id="id" placeholder="article-123" {...register('id')} />
              {errors.id && <p className="text-sm text-danger">{errors.id.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="archiver">Archiver</Label>
              <Select id="archiver" disabled={archiversLoading} {...register('archiver')}>
                {availableArchivers.map((option) => (
                  <option value={option} key={option}>
                    {option}
                  </option>
                ))}
              </Select>
              {archiversError && (
                <p className="text-xs text-warning">Unable to load archivers list. Using defaults.</p>
              )}
            </div>
            <div className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500">
              <p className="font-semibold text-slate-600">What happens?</p>
              <p className="mt-2">
                <strong>{selectedArchiver === 'all' ? 'All archivers' : selectedArchiver}</strong>{' '}
                will run immediately. Choosing <strong>all</strong> enqueues a background task and you
                can track progress on the dashboard.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3">
              <Button type="button" variant="secondary" onClick={() => reset()} disabled={submitting}>
                Reset
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Submitting…' : 'Queue Save'}
              </Button>
            </div>
          </form>
          {message && <p className="mt-4 text-sm text-success">{message}</p>}
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </CardContent>
      </Card>
    </section>
  )
}

function isTaskAccepted(result: SaveResponse | TaskAccepted): result is TaskAccepted {
  return (result as TaskAccepted).task_id !== undefined
}
