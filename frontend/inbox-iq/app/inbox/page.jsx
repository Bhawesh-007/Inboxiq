import React from 'react'
import Sidebar from '../Components/Sidebar'
import Emaillist from '../Components/Emaillist'
export default function InboxPage() {
  return (
    <div style={{ display: "flex", height: "100vh", background: "#0a0a0a" }}>
      <Sidebar />
      <div style={{ width: "340px", background: "#0d0d0d", borderRight: "1px solid #1e1e1e" , color: "#fff"}}>
        {<Emaillist/>}
      </div>
      <div style={{ flex: 1, background: "#0a0a0a" }}>
        {/* EmailDetail goes here later */}
      </div>
    </div>
  )
}