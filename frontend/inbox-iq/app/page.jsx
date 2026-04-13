"use client"
import React from 'react'
import Sidebar from './Components/Sidebar'
import Emaillist from './Components/Emaillist'
import Emaildetail from './Components/Emaildetail'
import { useState } from 'react'
function page() {
  const [selectedId, setSelectedId] = useState(null);
  return (
    <div className=' flex  h-screen'>
      <Sidebar/>
      <Emaillist onEmailClick = {setSelectedId}/>
      <Emaildetail emailId={selectedId} />
    </div>
  )
}

export default page