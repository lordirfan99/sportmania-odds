import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// ── Error Boundary to catch rendering errors ──
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: '' };
  }
  static getDerivedStateFromError(error) {
    return { error: error.message || String(error), info: '' };
  }
  componentDidCatch(error, info) {
    this.setState({ info: info.componentStack || '' });
    console.error('React Error:', error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          background: '#0a0a0f', color: '#ff3355', padding: '24px',
          fontFamily: 'monospace', minHeight: '100vh',
        }}>
          <h2 style={{ color: '#ff3355', marginBottom: 12 }}>⚠️ Render Error</h2>
          <pre style={{ color: '#ffcc00', fontSize: 12, whiteSpace: 'pre-wrap' }}>
            {this.state.error}
          </pre>
          {this.state.info && (
            <pre style={{ color: '#8888aa', fontSize: 10, marginTop: 12, whiteSpace: 'pre-wrap' }}>
              {this.state.info}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Render with error boundary ──
const root = document.getElementById('root');
try {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>
  );
} catch (e) {
  root.innerHTML = `<div style="color:#f35;padding:20px;font-family:monospace">
    <h2>⚠️ Fatal Error</h2>
    <pre>${e.message || e}</pre>
  </div>`;
}
