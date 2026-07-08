"use client";
import React, { useState } from 'react'
import Sidebar from '../Components/Sidebar'
import Emaillist from '../Components/Emaillist'
import Emaildetail from '../Components/Emaildetail'

export default function InboxPage() {
  const [selectedEmailId, setSelectedEmailId] = useState(null);

  return (
    <div style={{ display: "flex", height: "100vh", background: "#0a0a0a" }}>
      <Sidebar />
      <div style={{ width: "340px", background: "#0d0d0d", borderRight: "1px solid #1e1e1e" , color: "#fff"}}>
        <Emaillist onEmailClick={setSelectedEmailId} />
      </div>
      <div style={{ flex: 1, background: "#0a0a0a" }}>
        <Emaildetail emailId={selectedEmailId} />
      </div>
    </div>
  )
}