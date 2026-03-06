import { BrowserRouter, Routes, Route } from 'react-router-dom'
import LandingPage from './pages/LandingPage.jsx'
import ThankYouPage from './pages/ThankYouPage.jsx'

const styles = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f4f8;
    color: #1a1a2e;
    min-height: 100vh;
  }
`

export default function App() {
  return (
    <>
      <style>{styles}</style>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/thank-you" element={<ThankYouPage />} />
          <Route path="/error" element={<ErrorPage />} />
        </Routes>
      </BrowserRouter>
    </>
  )
}

function ErrorPage() {
  const params = new URLSearchParams(window.location.search)
  const reason = params.get('reason') || 'unknown'
  const messages = {
    consent_denied: 'The Microsoft consent was declined. Please try again and accept the permissions to proceed.',
    invalid_tenant: 'We could not identify your Microsoft tenant. Please contact us for assistance.',
    missing_state: 'Your session has expired. Please start the process again.',
    invalid_job: 'This assessment link is no longer valid. Please request a new one.',
  }
  return (
    <div style={{ display:'flex', justifyContent:'center', alignItems:'center', minHeight:'100vh' }}>
      <div style={{ maxWidth:480, padding:32, background:'white', borderRadius:12, boxShadow:'0 4px 24px rgba(0,0,0,0.1)', textAlign:'center' }}>
        <div style={{ fontSize:48, marginBottom:16 }}>⚠️</div>
        <h1 style={{ color:'#cc0000', marginBottom:12 }}>Something went wrong</h1>
        <p style={{ color:'#555', lineHeight:1.6 }}>{messages[reason] || 'An unexpected error occurred. Please contact us.'}</p>
        <a href="/" style={{ display:'inline-block', marginTop:24, padding:'10px 24px', background:'#003087', color:'white', borderRadius:6, textDecoration:'none' }}>
          Start Over
        </a>
      </div>
    </div>
  )
}
