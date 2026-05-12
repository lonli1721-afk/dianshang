import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { installDomMutationGuard } from './domMutationGuard'
import './index.css'

installDomMutationGuard()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
