import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './theme/index.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('GPTHEIST DESK: #root not found in the document.');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>
);
