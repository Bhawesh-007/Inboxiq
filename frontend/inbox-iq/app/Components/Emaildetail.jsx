"use client"
import React from 'react'
import './Emaildetail.css'
import { useState, useEffect } from 'react'
// now here i will render the details and body of the email that is selected


function Emaildetail({ emailId }) {
    const [email, setEmail] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [prevEmailId, setPrevEmailId] = useState(null);

    if (emailId !== prevEmailId) {
        setPrevEmailId(emailId);
        setLoading(true);
        setError(null);
    }

    //see what  i want now is to load data of email in a varriable so 
    //that i can use it for updating the database wwhenever i clik on a email
    useEffect(() => {
        if (!emailId) return;
        fetch(`http://localhost:5003/emails/${emailId}`)
            .then((res) => {
                if (!res.ok) throw new Error('Failed to fetch email details');
                return res.json();
            })
            .then((data) => {
                if (data.error) {
                    console.error('Backend error:', data.error);
                    setError(data.error);
                    setEmail(null);
                } else {
                    setEmail(data);
                    setError(null);
                }
                setLoading(false);
            })
            .catch((err) => {
                console.error('Fetch error:', err);
                setError(err.message);
                setEmail(null);
                setLoading(false);
            });
    }, [emailId]);
    if (!emailId) return <div className="email-empty">Select an email to read</div>
    if (loading) return <div className="email-loading">Loading...</div>
    if (error) return <div className="email-empty">Error: {error}</div>
    if (!email) return null;
    return (
        <div className="email-detail">
            <div className="email-header">
                <div className="email-subject">{email.subject}</div>
                <div className="email-meta">
                    <div className="email-from">From: <span>{email.from}</span></div>
                    <div className="email-date">{email.date}</div>
                </div>
            </div>
            {email.classification && email.classification.summary && (
                <div className="email-summary">
                    <div className="email-summary-title">
                        <svg className="ai-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                            <path d="m5 3 1 2.5L8.5 6 6 7 5 9.5 4 7 1.5 6 4 5.5z" fill="currentColor" />
                            <path d="m19 17 1 2.5 2.5.5-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1z" fill="currentColor" />
                        </svg>
                        <span>AI Classification Reason</span>
                    </div>
                    <div className="email-summary-text">
                        {email.classification.summary}
                    </div>
                </div>
            )}
            <div className="email-body" dangerouslySetInnerHTML={{ __html: email.body }} />
        </div>
    )
}

export default Emaildetail