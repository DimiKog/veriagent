import type { RegistrationRequestStatusResponse } from '../types'

export type RegistrationUiPhase =
  | 'idle'
  | 'requested'
  | 'proof_required'
  | 'proof_verified'
  | 'pending_approval'
  | 'approved'
  | 'credentials_claimed'
  | 'rejected'
  | 'expired'

export function phaseFromStatus(
  status: RegistrationRequestStatusResponse | null,
  justCreated: boolean,
): RegistrationUiPhase {
  if (!status) return justCreated ? 'requested' : 'idle'
  if (status.status === 'rejected') return 'rejected'
  if (status.status === 'expired') return 'expired'
  if (status.status === 'approved') {
    if (status.credentials_claimed) return 'credentials_claimed'
    return 'approved'
  }
  if (status.status === 'pending') {
    if (status.proof_submitted_at) return 'pending_approval'
    return 'proof_required'
  }
  return justCreated ? 'requested' : 'idle'
}

export function phaseLabel(phase: RegistrationUiPhase): string {
  switch (phase) {
    case 'requested':
      return 'Requested'
    case 'proof_required':
      return 'Proof required'
    case 'proof_verified':
      return 'Proof verified'
    case 'pending_approval':
      return 'Pending approval'
    case 'approved':
      return 'Approved'
    case 'credentials_claimed':
      return 'Credentials claimed'
    case 'rejected':
      return 'Rejected'
    case 'expired':
      return 'Expired'
    default:
      return 'Not started'
  }
}

export function shouldContinueRegistrationPoll(
  status: RegistrationRequestStatusResponse | null,
): boolean {
  if (!status) return true
  if (status.status === 'rejected' || status.status === 'expired') return false
  if (status.status === 'approved') {
    // Keep polling until credentials are claimed (or no longer available).
    return status.credentials_available && !status.credentials_claimed
  }
  return status.status === 'pending'
}
