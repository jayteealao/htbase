import axios, { AxiosError } from 'axios'

const envBaseURL = import.meta.env.VITE_API_BASE_URL as string | undefined
const baseURL = envBaseURL ?? '/api'

export const apiClient = axios.create({
  baseURL,
  timeout: 30_000,
})

apiClient.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<ApiError>) => {
    if (error.response) {
      const { status, data } = error.response
      console.error('API error', status, data)
    } else {
      console.error('API error', error.message)
    }
    return Promise.reject(error as Error)
  },
)

export type ApiError = {
  detail?: string
}
