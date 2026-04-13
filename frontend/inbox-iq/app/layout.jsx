import "./globals.css"

export const metadata = {
  title: "InboxIQ",
  description: "AI Email Intelligence",
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}