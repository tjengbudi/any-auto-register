import type { Catalog } from '@/i18n'

export const TASK_STATUS_VARIANTS: Record<string, any> = {
  pending: 'secondary',
  claimed: 'secondary',
  running: 'default',
  succeeded: 'success',
  failed: 'danger',
  interrupted: 'warning',
  cancel_requested: 'warning',
  cancelled: 'warning',
}

export const TERMINAL_TASK_STATUSES = new Set([
  'succeeded',
  'failed',
  'interrupted',
  'cancelled',
])

export function isTerminalTaskStatus(status: string) {
  return TERMINAL_TASK_STATUSES.has(status)
}

export function getTaskStatusText(status: string, catalog: Catalog) {
  switch (status) {
    case 'succeeded':
      return catalog.tasks.statusSucceeded
    case 'failed':
      return catalog.tasks.statusFailed
    case 'interrupted':
      return catalog.tasks.statusInterrupted
    case 'cancelled':
      return catalog.tasks.statusCancelled
    case 'cancel_requested':
      return catalog.tasks.statusCancelRequested
    case 'running':
      return catalog.tasks.statusRunning
    case 'claimed':
      return catalog.tasks.statusClaimed
    case 'pending':
      return catalog.tasks.statusPending
    default:
      return status
  }
}
