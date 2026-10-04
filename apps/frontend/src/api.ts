export interface Priority {
  low: 'low';
  normal: 'normal';
  high: 'high';
  critical: 'critical';
}

export interface WorkflowStatus {
  RECEIVED: 'RECEIVED';
  VALIDATED: 'VALIDATED';
  QUEUED: 'QUEUED';
  PROCESSING: 'PROCESSING';
  AWAITING_REVIEW: 'AWAITING_REVIEW';
  COMPLETED: 'COMPLETED';
  FAILED: 'FAILED';
  DEAD_LETTERED: 'DEAD_LETTERED';
}

export interface OperationalRequestCreate {
  subject: string;
  body: string;
  requester: string;
  priority: string;
}

export interface RequestDetail {
  request_id: string;
  correlation_id: string;
  status: string;
  request: OperationalRequestCreate;
  result: any;
  error_code: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface RequestAccepted {
  request_id: string;
  correlation_id: string;
  status: string;
  created_at: string;
}

const API_BASE = "http://localhost:8000/api/v1";

export const api = {
  submitRequest: async (data: OperationalRequestCreate): Promise<RequestAccepted> => {
    const res = await fetch(`${API_BASE}/requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to submit request");
    return res.json();
  },

  getRequest: async (requestId: string): Promise<RequestDetail> => {
    const res = await fetch(`${API_BASE}/requests/${requestId}`);
    if (!res.ok) throw new Error("Failed to fetch request");
    return res.json();
  },

  approveRequest: async (requestId: string): Promise<{ request_id: string; status: string }> => {
    const res = await fetch(`${API_BASE}/requests/${requestId}/approve`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("Failed to approve request");
    return res.json();
  }
};
