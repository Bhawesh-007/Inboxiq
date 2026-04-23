    "use client"
    import React from 'react'
    import './Emaildetail.css'
    import { useState , useEffect } from 'react'
    // now here i will render the details and body of the email that is selected


    function Emaildetail({emailId}) {
    const [email,setEmail] = useState(null);
    const [loading , setLoading] = useState(true);
    const [error, setError] = useState(null);
    useEffect(()=>{
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
    if(!email)return null;
    return (
      <div className="email-detail">
        <div className="email-body" dangerouslySetInnerHTML={{ __html: email.body }} />
      </div>
    )
    }

    export default Emaildetail