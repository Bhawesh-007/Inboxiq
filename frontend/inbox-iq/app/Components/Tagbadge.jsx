import React from 'react'
 const tagStyles = {
    urgent:   { background: "#2a1010", color: "#e05c5c", border: "1px solid #e05c5c22" },
    deadline: { background: "#1a1a0a", color: "#d4a853", border: "1px solid #d4a85322" },
    action:   { background: "#0a1a1a", color: "#4db8b8", border: "1px solid #4db8b822" },
    fyi:      { background: "#111",    color: "#666",    border: "1px solid #2a2a2a"   },
    spam:     { background: "#151015", color: "#aa55aa", border: "1px solid #aa55aa22" },
    pdf:      { background: "#0a120a", color: "#5a9e5a", border: "1px solid #5a9e5a22" },
  }
  //now what we will do is that pass a prop to this from email list and here i will just customize that element based on the tag type and the text will be the tag name itself. so this will be a reusable component which will take the tag name as prop and then render that tag with appropriate styles.
function Tagbadge({tag}) {
    const style = tagStyles[tag]||tagStyles[fyi]
  return (
    <span className = "tag" style = {{...style,
      fontSize: "12px",
      padding: "2px 7px",
      borderRadius: "3px",
      textTransform: "uppercase",
      letterSpacing: "0.06em",
      fontFamily: "monospace",
    cursor : "pointer"}}>{tag}</span>
  )
}

export default Tagbadge