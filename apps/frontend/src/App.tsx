import { useState, useEffect } from 'react';
import { api, OperationalRequestCreate, RequestDetail } from './api';
import './index.css';

function App() {
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState('low');
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [requestDetail, setRequestDetail] = useState<RequestDetail | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (polling && activeRequestId) {
      interval = setInterval(async () => {
        try {
          const detail = await api.getRequest(activeRequestId);
          setRequestDetail(detail);
          if (['COMPLETED', 'FAILED'].includes(detail.status)) {
            setPolling(false);
          }
        } catch (err) {
          console.error(err);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [polling, activeRequestId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const data: OperationalRequestCreate = {
        subject,
        body,
        requester: "local_demo_user",
        priority
      };
      
      const res = await api.submitRequest(data);
      setActiveRequestId(res.request_id);
      
      // Fetch initial details
      const detail = await api.getRequest(res.request_id);
      setRequestDetail(detail);
      
      setSubject('');
      setBody('');
      setPolling(true);
    } catch (err: any) {
      setError(err.message || 'Error submitting request');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!activeRequestId) return;
    try {
      await api.approveRequest(activeRequestId);
      const detail = await api.getRequest(activeRequestId);
      setRequestDetail(detail);
    } catch (err: any) {
      setError(err.message || 'Error approving request');
    }
  };

  const handleDemoClick = () => {
    setSubject("Update router configurations");
    setBody("Need to update router X configurations in DC-01 according to the new policy standard.");
    setPriority("normal");
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>OpsPilot</h1>
        <div className="demo-badge">Local Demo Environment</div>
      </header>

      <div className="grid">
        <div className="card">
          <h2>Submit Request</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Subject</label>
              <input 
                type="text" 
                className="form-control" 
                value={subject} 
                onChange={e => setSubject(e.target.value)} 
                required 
              />
            </div>
            
            <div className="form-group">
              <label>Body</label>
              <textarea 
                className="form-control" 
                rows={4} 
                value={body} 
                onChange={e => setBody(e.target.value)} 
                required 
              />
            </div>
            
            <div className="form-group">
              <label>Priority</label>
              <select 
                className="form-control" 
                value={priority} 
                onChange={e => setPriority(e.target.value)}
              >
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            
            <button type="submit" className="btn" disabled={loading}>
              {loading ? <div className="spinner"></div> : 'Submit Workflow'}
            </button>
            <button type="button" className="btn" style={{background: 'var(--surface-color)', border: '1px solid var(--border-color)'}} onClick={handleDemoClick}>
              Fill Demo Data
            </button>
            
            {error && <div style={{ color: 'var(--error)', marginTop: '1rem', fontSize: '0.875rem' }}>{error}</div>}
          </form>
        </div>

        <div className="card">
          <h2>Workflow Status</h2>
          
          {!activeRequestId && (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem 0' }}>
              No active request. Submit one to see its status here.
            </div>
          )}
          
          {activeRequestId && requestDetail && (
            <div>
              <div style={{ marginBottom: '1rem' }}>
                <span className={`status-badge status-${requestDetail.status}`}>
                  {requestDetail.status}
                </span>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                  ID: {requestDetail.request_id}
                </div>
              </div>
              
              <div className="timeline">
                <div className="timeline-item">
                  <strong>Received</strong>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{new Date(requestDetail.created_at).toLocaleString()}</div>
                </div>
                
                {['PROCESSING', 'AWAITING_REVIEW', 'COMPLETED', 'FAILED'].includes(requestDetail.status) && (
                  <div className="timeline-item">
                    <strong>Processing Started</strong>
                  </div>
                )}
                
                {['AWAITING_REVIEW', 'COMPLETED', 'FAILED'].includes(requestDetail.status) && (
                  <div className="timeline-item">
                    <strong>Review & Recommendation</strong>
                  </div>
                )}
              </div>
              
              {requestDetail.status === 'AWAITING_REVIEW' && (
                <div style={{ marginTop: '1.5rem', padding: '1rem', border: '1px dashed var(--warning)', borderRadius: '8px' }}>
                  <h3 style={{ fontSize: '1rem', color: 'var(--warning)', marginBottom: '0.5rem' }}>Human Review Required</h3>
                  <p style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>Please review the workflow and approve to proceed.</p>
                  <button className="btn btn-success" onClick={handleApprove}>Approve & Complete</button>
                </div>
              )}
              
              {/* Optional: if recommendation was stored in result, we could display it here. 
                  Currently, we didn't save the recommendation explicitly to the request_detail table, 
                  but in a real system we would expose it. */}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
