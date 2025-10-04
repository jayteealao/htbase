export type SaveRecord = {
  rowid: number
  id: string
  url: string
  name?: string | null
  status?: string | null
  success: number
  exit_code?: number | null
  saved_path?: string | null
  file_exists: boolean
  relative_path?: string | null
  archiver?: string | null
  created_at?: string | null
}

export type SaveResponse = {
  ok: boolean
  exit_code?: number | null
  saved_path?: string | null
  id: string
  db_rowid?: number | null
}

export type TaskAccepted = {
  task_id: string
  count: number
}

export type HtSendResponse = {
  ok: boolean
  exit_code: number | null
}
