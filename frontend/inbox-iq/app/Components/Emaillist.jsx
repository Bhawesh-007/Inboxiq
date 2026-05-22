"use client"
import React from 'react'
import './Emailist.css'
import { useEffect, useState } from 'react';
import Tagbadge from './Tagbadge'


//see now i have configured the gmail inbox of mine now here i will connect 
//to that api and would render emails here
//now to show email body i will first choose the selected email id for that i will pass down it in a usestate
function Emaillist({ onEmailClick }) {
  const [emails, setEmails] = useState([]);
  //this is a hook which will store all the emails in the array
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  //first i will set hooks to track page and nextpage token
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const per_page = 10;
  useEffect(() => {
    fetch(`http://localhost:5003/emails?page=${page}&per_page=${per_page}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch emails');
        return res.json();
      })
      .then((data) => {
        if (data.error) {
          console.error('Backend error:', data.error);
          setError(data.error);
          setEmails([]);
        } else {
          setEmails(data.emails || []);
          setHasMore(data.pagination?.has_more || false);
          setError(null);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('Fetch error:', err);
        setError(err.message);
        setEmails([]);
        setLoading(false);
      });
  }, [page]); //run every time when page changes
  const handleClick = (email) => {
    setSelectedId(email.id);
    onEmailClick(email.id)
  }
  if (loading) return <div className="loading">Loading emails ....</div>
  if (error) return <div className="error">Error: {error}</div>
  return (
    <div className="supclass flex flex-col gap-3">
      <div className="header text-white text-2xl font-bold">
        <div className="head">Inbox</div>
      </div>

      <div className="emaillist flex flex-col gap-1.5">
        {emails.map((email) => (
          <div key={email.id}
            className={`email-box ${selectedId === email.id ? "selected" : ""}`}
            onClick={() => handleClick(email)}
          >
            <div className='email-header flex items-center gap-2'>
              <span className='sender'>{email.from}</span>
              <span className='time'>{email.date}</span>
              <Tagbadge tag={email.label} />
            </div>
            <div className='email-subject'>{email.subject}</div>
          </div>
        ))}
      </div>
      <div className="pagination-container">
        <button
          className="pagination-btn"
          disabled={page == 1 || loading}
          onClick={() => setPage(page - 1)}
        >
          Prev
        </button>
        <span className='page-indicator'>Page{page}</span>
        <button
          className="pagination-btn"
          disabled={!hasMore || loading}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>

  )


}
export default Emaillist;