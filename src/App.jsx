import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import MatchDetail from './components/MatchDetail';

export default function App() {
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
