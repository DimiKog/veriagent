import { ApiError } from '../api/client'

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}
