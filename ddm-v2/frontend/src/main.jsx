import React from 'react';
import { createRoot } from 'react-dom/client';

import '../../src/ddm_v2/static/legacy_ui/base.css';
import './index.css';
import App from '../../src/ddm_v2/static/legacy_ui/app.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
