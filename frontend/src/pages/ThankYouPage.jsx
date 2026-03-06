export default function ThankYouPage() {
  const params = new URLSearchParams(window.location.search)
  const email = params.get('email') || 'your email address'

  return (
    <div style={{ display:'flex', justifyContent:'center', alignItems:'center', minHeight:'100vh', padding:24 }}>
      <div style={{ background:'white', borderRadius:16, boxShadow:'0 8px 32px rgba(0,0,0,0.12)', padding:'48px 40px', maxWidth:520, width:'100%', textAlign:'center' }}>
        <div style={{ fontSize:64, marginBottom:16 }}>✅</div>
        <h1 style={{ color:'#003087', fontSize:26, marginBottom:12 }}>Consent Received!</h1>
        <p style={{ color:'#444', fontSize:15, lineHeight:1.7, marginBottom:24 }}>
          Thank you. Your M365 Security Assessment is now running. We'll send your comprehensive report to:
        </p>
        <div style={{ background:'#f0f4ff', borderRadius:8, padding:'12px 20px', marginBottom:24, fontSize:15, fontWeight:600, color:'#003087' }}>
          {email}
        </div>
        <p style={{ color:'#666', fontSize:14, lineHeight:1.7 }}>
          The audit typically completes within <strong>30–60 minutes</strong> depending on your tenant size.
          You can safely close this window.
        </p>
        <div style={{ marginTop:32, padding:'16px', background:'#f8faff', borderRadius:8, fontSize:13, color:'#555', lineHeight:1.6 }}>
          <strong>What happens next:</strong><br/>
          Our system is auditing your Entra ID, Exchange, SharePoint, Teams, Purview, and Admin Portal settings.
          An AI-powered analysis will generate your personalized security report with a prioritized remediation roadmap.
        </div>
        <p style={{ marginTop:24, fontSize:12, color:'#aaa' }}>
          Didn't receive the email? Check your spam folder or contact us.
        </p>
      </div>
    </div>
  )
}
