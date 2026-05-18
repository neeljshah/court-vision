import type { Metadata } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import './globals.css'

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const jetbrains = JetBrains_Mono({ subsets: ['latin'], variable: '--font-jetbrains' })

export const metadata: Metadata = {
  title: 'Neel Shah — Quantitative Researcher · Sports-Market Pricing',
  description: 'Possession-level NBA simulator. Broadcast video → spatial features → priced positions. +14 bps CLV vs Pinnacle close on 312 settled picks.',
  openGraph: {
    title: 'Neel Shah — Quantitative Researcher · Sports-Market Pricing',
    description: 'Possession-level NBA simulator. +14 bps CLV vs Pinnacle on 312 picks.',
    type: 'website',
    images: [{ url: '/og.svg', width: 1200, height: 630 }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Neel Shah — Quantitative Researcher',
    description: '+14 bps CLV vs Pinnacle on 312 settled picks.',
    images: ['/og.svg'],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrains.variable}`}>
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body>{children}</body>
    </html>
  )
}
