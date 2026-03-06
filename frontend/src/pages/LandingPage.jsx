import { useState } from 'react'
import axios from 'axios'

const pageStyle = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  minHeight: '100vh',
  padding: '24px',
}

const cardStyle = {
  background: 'white',
  borderRadius: 16,
  boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
  padding: '48px 40px',
  maxWidth: 520,
  width: '100%',
}

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  border: '1.5px solid #ddd',
  borderRadius: 8,
  fontSize: 15,
  outline: 'none',
  transition: 'border-color 0.2s',
}

const btnStyle = (loading) => ({
  width: '100%',
  padding: '14px',
  background: loading ? '#aaa' : '#003087',
  color: 'white',
  border: 'none',
  borderRadius: 8,
  fontSize: 16,
  fontWeight: 600,
  cursor: loading ? 'not-allowed' : 'pointer',
  marginTop: 8,
  transition: 'background 0.2s',
})

export default function LandingPage() {
  const [email, setEmail] = useState('')
  const [company, setCompany] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const res = await axios.post('/api/start', { email, company })
      window.location.href = res.data.consent_url
    } catch (err) {
      if (err.response?.status === 409) {
        setError('An assessment for this email address is already in progress. Please check your inbox.')
      } else {
        setError('Something went wrong. Please try again.')
      }
      setLoading(false)
    }
  }

  return (
    <div style={pageStyle}>
      <div style={cardStyle}>
        <div style={{ textAlign:'center', marginBottom:32 }}>
          <div style={{ width:160, height:60, background:'#e8edf5', margin:'0 auto 20px', borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:'#888', fontSize:12, border:'2px dashed #ccc' }}>
            [YOUR LOGO]
          </div>
          <h1 style={{ fontSize:24, color:'#003087', fontWeight:700 }}>Free M365 Security Assessment</h1>
          <p style={{ color:'#666', marginTop:8, lineHeight:1.6, fontSize:14 }}>
            We'll audit your Microsoft 365 environment and deliver a comprehensive security report directly to your inbox.
          </p>
        </div>

        <div style={{ background:'#f8faff', borderRadius:10, padding:'16px 20px', marginBottom:28 }}>
          <p style={{ fontSize:13, fontWeight:600, color:'#003087', marginBottom:8 }}>What's included in your report:</p>
          <ul style={{ fontSize:13, color:'#444', paddingLeft:18, lineHeight:1.8 }}>
            <li>Microsoft Entra ID (Azure AD) audit</li>
            <li>Exchange Online security review</li>
            <li>SharePoint Online assessment</li>
            <li>Microsoft Teams security posture</li>
            <li>Microsoft Purview compliance review</li>
            <li>AI-powered remediation roadmap</li>
          </ul>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom:16 }}>
            <label style={{ display:'block', fontSize:13, fontWeight:600, marginBottom:6, color:'#333' }}>
              Company Name
            </label>
            <input
              style={inputStyle}
              type="text"
              required
              placeholder="Acme Corporation"
              value={company}
              onChange={e => setCompany(e.target.value)}
            />
          </div>

          <div style={{ marginBottom:20 }}>
            <label style={{ display:'block', fontSize:13, fontWeight:600, marginBottom:6, color:'#333' }}>
              Email Address (report delivery)
            </label>
            <input
              style={inputStyle}
              type="email"
              required
              placeholder="admin@yourcompany.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>

          {error && (
            <div style={{ background:'#fff5f5', border:'1px solid #ffcccc', borderRadius:6, padding:'10px 14px', marginBottom:16, fontSize:13, color:'#cc0000' }}>
              {error}
            </div>
          )}

          <button type="submit" style={btnStyle(loading)} disabled={loading}>
            {loading ? 'Preparing consent...' : 'Start Free Assessment →'}
          </button>
        </form>

        <div style={{ marginTop:20, padding:'14px 16px', background:'#fffbf0', borderRadius:8, border:'1px solid #ffe0a0' }}>
          <p style={{ fontSize:12, color:'#775500', lineHeight:1.6 }}>
            <strong>Next step:</strong> You'll be redirected to Microsoft to grant read-only access to your M365 environment. A Global Administrator account is required. We never modify your data.
          </p>
        </div>

        <p style={{ fontSize:11, color:'#aaa', textAlign:'center', marginTop:20 }}>
          Your report will be emailed within 30–60 minutes of consent.
        </p>
      </div>
    </div>
  )
}
