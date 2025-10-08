import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { Label } from '../../components/ui/Label'
import { sendHtCommand } from '../../api/ht'

const envPreviewUrl = import.meta.env.VITE_HT_PREVIEW_URL as string | undefined
const PREVIEW_URL = envPreviewUrl ?? 'http://localhost:7681'

export default function HtConsolePage() {
  const [command, setCommand] = useState('echo hello')
  const [marker, setMarker] = useState('__DONE__')
  const [timeoutSeconds, setTimeoutSeconds] = useState(15)

  const mutation = useMutation({
    mutationFn: sendHtCommand,
  })

  return (
    <section className="grid gap-6 xl:grid-cols-[2fr,1fr]">
      <Card className="h-full">
        <CardHeader>
          <CardTitle>Live Preview</CardTitle>
        </CardHeader>
        <CardContent>
          <iframe
            title="ht preview"
            src={PREVIEW_URL}
            className="h-[600px] w-full rounded-xl border border-slate-200"
          />
          <p className="mt-3 text-xs text-slate-400">
            Preview URL configurable via <code>VITE_HT_PREVIEW_URL</code>.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Command Console</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="command">Command</Label>
            <textarea
              id="command"
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              className="min-h-[140px] w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200"
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="marker">Wait Marker</Label>
              <Input
                id="marker"
                value={marker}
                onChange={(event) => setMarker(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="timeout">Timeout (s)</Label>
              <Input
                id="timeout"
                type="number"
                min={1}
                value={timeoutSeconds}
                onChange={(event) =>
                  setTimeoutSeconds(Number.parseInt(event.target.value, 10) || 1)
                }
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              onClick={() =>
                mutation.mutate({
                  payload: `${command}\r`,
                  waitMarker: marker || undefined,
                  timeout: timeoutSeconds,
                })
              }
              disabled={mutation.isPending || !command.trim()}
            >
              {mutation.isPending ? 'Sending…' : 'Send Command'}
            </Button>
            <Button variant="ghost" onClick={() => setCommand('')}>
              Clear
            </Button>
          </div>
          {mutation.isError && (
            <p className="text-sm text-danger">
              {mutation.error instanceof Error ? mutation.error.message : 'Command failed.'}
            </p>
          )}
          {mutation.isSuccess && (
            <p className="text-sm text-success">
              Command queued (exit code {mutation.data.exit_code ?? 'unknown'}).
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
