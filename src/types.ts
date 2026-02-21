export interface User {
  id: string;
  firstname: string;
  lastname: string;
  email: string;
  languages: string[];
  skills: string[];
  roles: string[];
  organization_id: string | null;
  app_role: 'admin' | 'user';
  created_at: string;
}

export interface Organization {
  id: string;
  name: string;
  account_types: string[];
  created_at: string;
}

export interface StudioCompany {
  id: string;
  organization_id: string;
  studio_id: string;
  name: string;
  environment: 'test' | 'prod';
  created_at: string;
}

export interface SystemGroup {
  id: string;
  organization_id: string;
  tool: string;
  external_name: string;
  external_id: string | null;
  created_at: string;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface WorkflowStepDefinition {
  id: string;
  workflow_definition_id: string;
  step_order: number;
  name: string;
  label: string;
  type: 'auto' | 'manual';
  description: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_definition_id: string;
  organization_id: string | null;
  user_id: string | null;
  requested_by: string | null;
  status: 'pending' | 'running' | 'awaiting_input' | 'completed' | 'failed';
  current_step_order: number;
  created_at: string;
  completed_at: string | null;
}

export interface WorkflowStepExecution {
  id: string;
  execution_id: string;
  step_definition_id: string;
  step_order: number;
  status: 'pending' | 'running' | 'awaiting_input' | 'completed' | 'failed' | 'skipped';
  manual_input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  completed_by: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface StepResult {
  success: boolean;
  output?: Record<string, string>;
  error?: string;
}

export interface AuthRequest extends Express.Request {
  user?: User;
}

// Extend Express Request
declare global {
  namespace Express {
    interface Request {
      user?: User;
    }
  }
}
