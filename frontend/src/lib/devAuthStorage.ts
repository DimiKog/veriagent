/** Session-scoped dev auth keys — Admin and Console must never share a slot. */
export const ADMIN_DEV_AUTH_STORAGE_KEY = 'veriagent_admin_key'
export const AGENT_DEV_AUTH_STORAGE_KEY = 'veriagent_agent_api_key'

export function assertDistinctDevAuthStorageKeys(): void {
  const adminKey = ADMIN_DEV_AUTH_STORAGE_KEY as string
  const agentKey = AGENT_DEV_AUTH_STORAGE_KEY as string
  if (adminKey === agentKey) {
    throw new Error('Admin and agent dev auth storage keys must differ')
  }
}

function readSessionValue(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function writeSessionValue(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    // sessionStorage may be unavailable (private mode, quota, etc.)
  }
}

function clearSessionValue(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // ignore
  }
}

export function readAdminDevAuthKey(): string {
  return readSessionValue(ADMIN_DEV_AUTH_STORAGE_KEY)
}

export function writeAdminDevAuthKey(key: string): void {
  writeSessionValue(ADMIN_DEV_AUTH_STORAGE_KEY, key)
}

export function clearAdminDevAuthKey(): void {
  clearSessionValue(ADMIN_DEV_AUTH_STORAGE_KEY)
}

export function readAgentDevAuthKey(): string {
  return readSessionValue(AGENT_DEV_AUTH_STORAGE_KEY)
}

export function writeAgentDevAuthKey(key: string): void {
  writeSessionValue(AGENT_DEV_AUTH_STORAGE_KEY, key)
}

export function clearAgentDevAuthKey(): void {
  clearSessionValue(AGENT_DEV_AUTH_STORAGE_KEY)
}
