"use client";
import React from 'react'
import './Emailist.css'
import { useEffect, useState } from 'react';
import Tagbadge from './Tagbadge';
import { useWebSocket } from '../hooks/useWebSocket';

function Emaillist({ onEmailClick }) {
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [userId, setUserId] = useState(null);
  const per_page = 10;

  const { newEmails, clearNewEmails } = useWebSocket(userId);

  useEffect(() => {
    const loadEmails = () => {
      setLoading(true);
      fetch(`https://inboxiq-production-ec9c.up.railway.app/emails?page=${page}&per_page=${per_page}`)
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
            
            if (data.user_id && !userId) {
              setUserId(data.user_id);
            }
          }
          setLoading(false);
        })
        .catch((err) => {
          console.error('Fetch error:', err);
          setError(err.message);
          setEmails([]);
          setLoading(false);
        });
    };

    loadEmails(); // run immediately
  }, [page]); 

  const handleClick = (email) => {
    setSelectedId(email.id);
    onEmailClick(email.id);
    clearNewEmails();
  }

  const allEmails = [...newEmails, ...emails];

  if (loading && page === 1) return <div className="loading">Loading emails ....</div>
  if (error) return <div className="error">Error: {error}</div>

  return (
    <div className="supclass flex flex-col gap-3">
      <div className="header text-white text-2xl font-bold">
        <div className="head">Inbox</div>
      </div>

      {newEmails.length > 0 && (
        <div className="new-email-banner" onClick={clearNewEmails}>
          ↑ {newEmails.length} new email{newEmails.length > 1 ? "s" : ""} — click to dismiss
        </div>
      )}

      <div className="emaillist flex flex-col gap-1.5">
        {allEmails.map((email) => (
          <div key={email.id}
            className={`email-box ${selectedId === email.id ? "selected" : ""} ${
              newEmails.some((e) => e.id === email.id) ? "email-box--new" : ""
            }`}
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