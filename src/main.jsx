import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import MatchDetail from './components/MatchDetail';
import './index.css';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-dark-900">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/match/:matchId" element={<MatchDetail />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
