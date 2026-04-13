"use client"

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import './Sidebar.css'

function Sidebar() {
  const pathname = usePathname()

  const navItems = [
    { icon: "◈", label: "Inbox", href: "/inbox", badge: 12 },
    { icon: "◷", label: "Deadlines", href: "/deadlines", badge: 3 },
    { icon: "⊡", label: "PDFs", href: "/pdfs" },
    { icon: "◎", label: "Digest", href: "/digest" },
  ]

  const filterItems = [
    { icon: "⚡", label: "Urgent" },
    { icon: "◻", label: "Action needed" },
    { icon: "◌", label: "FYI only" },
    { icon: "✕", label: "Spam" },
  ]

  return (
    <div className='sidebar'>

      <div className='logo'>
        <h1>InboxIQ</h1>
        <p>AI Email Intelligence</p>
      </div>

      <div className='nav-items'>
        {navItems.map((item) => (
          <Link href={item.href} key={item.label} style={{ textDecoration: "none" }}>
            <div className={`nav-item ${pathname === item.href ? "active" : ""}`}>
              <span className='nav-icon'>{item.icon}</span>
              <span>{item.label}</span>
              {item.badge && <span className='badge'>{item.badge}</span>}
            </div>
          </Link>
        ))}
      </div>

      <div className='nav-section'>Filters</div>

      <div className='nav-items'>
        {filterItems.map((item) => (
          <div key={item.label} className='nav-item'>
            <span className='nav-icon'>{item.icon}</span>
            <span>{item.label}</span>
          </div>
        ))}
      </div>

      <div className='sidebar-footer'>
        <div className='avatar'>B</div>
        <div>
          <p className='account-name'>Bhawesh</p>
          <p className='account-email'>bhawesh@gmail.com</p>
        </div>
      </div>

    </div>
  )
}

export default Sidebar