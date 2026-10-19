import React from 'react';
import { createRoot } from 'react-dom/client';
import { MantineProvider, createTheme } from '@mantine/core';
import '@mantine/core/styles.css';
import '@mantine/dropzone/styles.css';
import './styles.css';
import App from './App.jsx';
import CandidateDiagnosisApp from './CandidateDiagnosisApp.jsx';
import './diagnosis.css';

const theme = createTheme({
  primaryColor: 'indigo',
  fontFamily: "'Inter', 'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif",
  defaultRadius: 'md',
  colors: {
    indigo: ['#eef3ff', '#dce8ff', '#bed0ff', '#98b1ff', '#7795f7', '#5a79e2', '#4564c7', '#3d57ac', '#33498e', '#2b3b72'],
  },
  components: {
    Button: { defaultProps: { radius: 'md' } },
    TextInput: { defaultProps: { radius: 'md' } },
    Textarea: { defaultProps: { radius: 'md' } },
    Paper: { defaultProps: { radius: 'lg' } },
  },
});

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <MantineProvider theme={theme}>
      {window.location.pathname.startsWith('/classic') ? <App /> : <CandidateDiagnosisApp />}
    </MantineProvider>
  </React.StrictMode>,
);
