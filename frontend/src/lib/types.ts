/** API types shared by every workspace. */

export type Role = 'AGENCY_REQUESTER' | 'OPS_AGENT' | 'ESCALATION_MANAGER' | 'OPS_LEAD'

export type Capability =
  | 'ops'
  | 'route'
  | 'agents'
  | 'side_conversations'
  | 'internal_notes'
  | 'escalate'
  | 'product_intelligence'
  | 'exports'
  | 'simulation'
  | 'override_assignment'

export const INTENTS = [
  'REFUND_DELAY',
  'CANCELLATION_LCD_WAIVER',
  'VOUCHER_CONFIRMATION_ISSUE',
  'AMENDMENT_NAME_DATE',
  'INVENTORY_RATE_SYNC_BUG',
  'SPECIAL_REQUEST',
  'SUPPLIER_OVERBOOKING_RELOCATION',
  'BILLING_INVOICE_DISPUTE',
] as const
export type Intent = (typeof INTENTS)[number]

export const PRIORITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
export const SLA_STATES = ['HEALTHY', 'AT_RISK', 'BREACHED', 'RESOLVED'] as const

export interface User {
  id: number
  email: string
  full_name: string
  role: Role
  region: string | null
  timezone: string
  skill_rank: number
  max_capacity: number
  is_online: boolean
  shift: string
  agency_id: number | null
}

export interface Agency {
  id: number
  code: string
  name: string
  tier: string
  region: string
  contact_email: string
}

export interface Booking {
  id: number
  tboh_id: string
  hotel_name: string
  supplier_name: string
  supplier_email: string | null
  destination_city: string
  destination_country: string
  region: string
  timezone: string
  check_in: string | null
  check_out: string | null
  lcd: string | null
  booking_status: string
  amount: number | null
  currency: string
  passenger_name: string
  agency_name: string | null
  agency_tier: string | null
  display_timezone?: string
  check_in_local?: string | null
  lcd_local?: string | null
}

export interface SlaView {
  state: 'HEALTHY' | 'AT_RISK' | 'BREACHED' | 'RESOLVED'
  governing_rule: string
  effective_due_at: string
  priority_due_at: string
  lcd_deadline: string | null
  checkin_deadline: string | null
  at_risk_threshold: number
  elapsed_ratio: number
  seconds_remaining: number
  minutes_remaining: number
  holiday_adjustment_applied: boolean
  expired_travel_deadline: boolean
  missing_dates: string[]
  reasons: string[]
  urgency_weight: number
}

export interface TicketRow {
  id: number
  ticket_number: string
  title: string
  description: string
  intent: string | null
  intent_label: string | null
  intent_confidence: number | null
  intent_source: string | null
  priority: string
  status: string
  queue: string
  region: string
  assigned_to: string | null
  assigned_user_id: number | null
  agency: string | null
  agency_id: number
  booking: Booking | null
  sla: SlaView
  escalated: boolean
  regional_holiday_flag: boolean
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface Message {
  id: number
  sender_name: string
  sender_role: string
  message_type: 'PUBLIC_REPLY' | 'INTERNAL_NOTE'
  content: string
  created_at: string
}

export interface SideMessage {
  id: number
  sender_email: string
  recipient_email: string
  content: string
  direction: string
  status: string
  created_at: string
}

export interface SideConversation {
  id: number
  ticket_id: number
  channel_type: string
  subject: string
  counterparty_name: string
  explicit_recipients: string[]
  created_by_group: string | null
  status: string
  created_at: string
  messages: SideMessage[]
}

export interface ActivityEvent {
  id: number
  event_type: string
  actor_name: string
  description: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface RelatedTicket {
  ticket_id: number
  ticket_number: string
  title: string
  intent: string | null
  status: string
  priority: string
  created_at: string | null
  link_type: string
  confidence: number
  reason: string | null
}

export interface CandidateScore {
  agent_id: number
  full_name: string
  region: string | null
  skill_rank: number
  active_load: number
  max_capacity: number
  region_match: number
  shift_match: number
  skill_component: number
  capacity_component: number
  total_score: number
}

export interface ExcludedCandidate {
  agent_id: number
  full_name: string
  region: string | null
  reasons: string[]
}

export interface RoutingAudit {
  id: number
  ticket_id: number
  candidates: CandidateScore[]
  excluded: ExcludedCandidate[]
  eligible_count: number
  selected_agent_id: number | null
  selected_agent: string | null
  selected_score: number | null
  decision_reason: string
  tie_break_applied: boolean
  triggered_by: string
  created_at: string
}

export interface CaseBrief {
  generated_at: string
  method: string
  tickets_in_case: number
  points: string[]
  sources: {
    ticket_ids: number[]
    booking_id: string | null
    message_count: number
    side_conversation_count: number
  }
}

export interface Escalation {
  id: number
  assigned_em: string | null
  assigned_em_id: number
  escalated_by: string | null
  previous_owner_id: number | null
  previous_status: string
  previous_queue: string
  reason: string
  escalated_at: string
}

export interface TransferRecord {
  id: number
  from_queue: string
  to_queue: string
  note: string | null
  preserved_side_conversations: number
  preserved_recipients: { conversation_id: number; recipients: string[] }[]
  created_at: string
}

export interface TicketDetail extends TicketRow {
  classification: {
    intent: string | null
    label: string | null
    confidence: number | null
    reasoning: string[]
    scores: Record<string, number>
    source: string | null
  }
  messages: Message[]
  side_conversations: SideConversation[]
  routing_audits: RoutingAudit[]
  activity_timeline: ActivityEvent[]
  transfers: TransferRecord[]
  escalations: Escalation[]
  case_brief: CaseBrief
  related_tickets: RelatedTicket[]
}

export interface SlaMatrix {
  priority_hours: Record<string, number>
  lcd_buffer_hours: number
  checkin_buffer_hours: number
  default_at_risk_threshold: number
  holiday_at_risk_threshold: number
}

export interface TicketListResponse {
  count: number
  tickets: TicketRow[]
  sla_matrix: SlaMatrix
}

export interface AgentWorkload {
  agent_id: number
  name: string
  region: string | null
  active_load: number
  max_capacity: number
  skill_rank: number
  is_online: boolean
}

export interface QueueSnapshot {
  totals: {
    tickets: number
    active: number
    at_risk: number
    breached: number
    escalated: number
    unassigned: number
  }
  sla_states: Record<string, number>
  sla_compliance: { compliance_pct: number; healthy: number; active: number; definition: string }
  by_region: { region: string; count: number }[]
  by_intent: { intent: string; label: string; count: number }[]
  by_priority: { priority: string; count: number }[]
  weekly_volume: { week: string; count: number }[]
  agent_workload: AgentWorkload[]
  next_travel: TicketRow[]
  tickets: TicketRow[]
  sla_matrix: SlaMatrix
}

export interface AgentBoardRow {
  agent_id: number
  name: string
  email: string
  region: string | null
  timezone: string
  skill_rank: number
  max_capacity: number
  active_load: number
  is_online: boolean
  shift: string
  shift_match_now: boolean
  eligible_generic: boolean
  utilization_pct: number
  reference_score: number
  resolved_tickets?: number
  avg_resolution_hours?: number | null
  on_shift_now?: boolean
}

export interface RoutingFormula {
  formula: string
  max_score: number
  weights: Record<string, number>
  variables: Record<string, string>
  hard_filters: string[]
  tie_break: string
}

export interface RoutingDecision {
  ticket_id: number
  ticket_number: string
  ticket_region: string
  sla_state: string
  urgency_weight: number
  candidates: CandidateScore[]
  excluded: ExcludedCandidate[]
  winner: CandidateScore | null
  tie_break_applied: boolean
  explanation?: string
  current_assignee_id?: number | null
}

export interface RoutingOutcome {
  ticket_id: number
  ticket_number: string
  assigned_to: {
    id: number | null
    name: string | null
    region: string | null
    skill_rank: number | null
    active_load: number | null
    max_capacity: number | null
  } | null
  decision: RoutingDecision & {
    score: number
    decision_reason: string
    assigned_agent_id: number | null
  }
  audit_id: number
  fifo_note: string
}

export interface EscalationQueue {
  counts: { escalated: number; at_risk: number; breached: number; healthy: number }
  managers: {
    id: number
    full_name: string
    region: string | null
    timezone: string
    active_escalations: number
    is_online: boolean
  }[]
  tickets: TicketRow[]
  viewer: string
}

export interface ProductIntelligence {
  window_days: number
  window_start: string
  tickets_in_window: number
  intent_distribution: { intent: string; label: string; count: number }[]
  supplier_complaints: { supplier: string; tickets: number }[]
  resolution_time_distribution: { bucket: string; count: number }[]
  resolution_stats: { resolved: number; avg_hours: number | null }
  weekly_trends: { week: string; count: number }[]
  refund_bottleneck: {
    open_refunds: number
    avg_open_age_hours: number
    avg_resolved_hours: number | null
    oldest_open: {
      ticket_number: string
      title: string
      supplier: string | null
      age_hours: number
    } | null
  }
  regional_performance: {
    region: string
    tickets: number
    breached: number
    resolved: number
    avg_resolution_hours: number | null
  }[]
  inventory_sync: { ticket_count: number; suppliers: string[]; ticket_numbers: string[] }
  themes: { name: string; category: string; occurrences: number; distinct_suppliers: number }[]
  theme_tags: {
    name: string
    category: string
    occurrences: number
    distinct_suppliers: number
    last_seen: string | null
  }[]
  data_notice: string
}

export interface BugSuggestion {
  supplier: string
  intent: string
  intent_label: string
  frequency: number
  ticket_ids: number[]
  ticket_numbers: string[]
  evidence: string[]
  period: { from: string; to: string }
  window_days: number
  confidence: string
  suggested_action: string
  related_ticket_links: number
}

export interface ProductBugRecord {
  bug_code: string
  title: string
  supplier: string
  intent: string | null
  intent_label: string | null
  frequency: number
  status: string
  suggested_action: string
  supporting_evidence: string
  related_ticket_ids: number[]
  window_start: string | null
  window_end: string | null
  created_at: string | null
}

export interface ExportJob {
  job_id: number
  job_uuid: string
  format: string
  status: string
  data_source: string
  requested_by: string
  total_rows: number
  rows_streamed: number
  duration_ms: number | null
  file_size_bytes: number | null
  file_size_mb: number | null
  throughput_rows_per_sec: number | null
  peak_memory_mb: number | null
  filters: Record<string, unknown> | null
  error_message: string | null
  created_at: string | null
  completed_at: string | null
  progress_pct: number
}

export interface ExportValidation {
  job_uuid: string
  result: string
  expected_rows: number
  actual_rows_in_file: number
  row_count_matches: boolean
  column_count: number
  file_size_bytes: number
  file_format: string
  readable: boolean
  duration_ms: number | null
  throughput_rows_per_sec: number | null
  peak_memory_mb: number | null
  note: string
}

export interface JourneyStep {
  name: string
  expected: string
  actual: string
  passed: boolean
  evidence: Record<string, unknown>
  duration_ms: number
  error: string | null
}

export interface JourneyResult {
  journey: string
  title: string
  started_at: string
  finished_at: string
  steps: JourneyStep[]
  steps_total: number
  steps_passed: number
  passed: boolean
  meta?: { title: string; agency: string; expected: string; workspace: string }
  console?: string
}

export interface SimStatus {
  database: { tickets: number; active: number }
  classifier_mode: string
  classifier_error: string | null
  internal_base_url: string
  datasets_are_synthetic: boolean
  journeys: { key: string; title: string; agency: string; expected: string; workspace: string }[]
  last_results_available: boolean
}


export interface AgentToolCall {
  tool: string
  args: Record<string, unknown>
  ok: boolean
  duration_ms: number
  preview: string
}

export interface AgentRecommendation {
  priority: 'P0' | 'P1' | 'P2'
  action: string
  rationale: string
}

export interface AgentResult {
  agent: string
  title: string
  status: 'OK' | 'ATTENTION' | 'SKIPPED' | 'ERROR'
  summary: string
  findings: string[]
  recommendations: AgentRecommendation[]
  confidence: number
  evidence: Record<string, unknown>
  tool_calls: AgentToolCall[]
  duration_ms: number
}

export interface AgentPlanItem extends AgentRecommendation {
  source_agent: string
}

export interface AgentRun {
  run_uuid: string
  ticket_id: number
  ticket_number: string | null
  objective: string
  status: 'COMPLETED' | 'PARTIAL' | 'FAILED'
  agent_count: number
  overall_confidence: number
  headline: string
  plan: AgentPlanItem[]
  agents: AgentResult[]
  duration_ms: number
  created_at: string
  created_by?: string
  needs_human?: string[]
  status_counts?: Record<string, number>
}

export interface AgentRegistryEntry {
  name: string
  title: string
  description: string
  tools: { name: string; description: string }[]
  external_model: string | null
  deterministic: boolean
}
