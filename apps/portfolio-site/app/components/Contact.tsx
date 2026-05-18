'use client'
import { motion } from 'framer-motion'
import { Mail } from 'lucide-react'

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
    </svg>
  )
}

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
    </svg>
  )
}

export default function Contact() {
  return (
    <section className="py-24 md:py-32 border-t border-[#1f1f2e]">
      <div className="max-w-6xl mx-auto px-6">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }} viewport={{ once: true, margin: '-100px' }}
          className="max-w-2xl">
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-3">Contact</p>
          <h2 className="text-3xl font-bold text-[#e7e7ee] mb-8">What I&apos;m Looking For</h2>
          <div className="space-y-4 text-[#9999a8] mb-8">
            <p className="leading-relaxed">Alt-data or sports-quant research. Seats where data engineering and modeling aren&apos;t siloed, because the edge in my experience is upstream of the model — in how the feature was extracted, cleaned, and timestamped — not in hyperparameter search.</p>
            <p className="leading-relaxed">I work best when the question is &quot;does this signal actually price into the market&quot; and the answer requires building something non-trivial to find out.</p>
          </div>
          <div className="flex flex-wrap gap-2 mb-10">
            {['Quant Research', 'Alt-Data', 'Founding Engineer', 'Sports Analytics'].map(tag => (
              <span key={tag} className="font-mono text-sm text-[#3b82f6] border border-[#3b82f6]/30 bg-[#3b82f6]/5 px-3 py-1.5 rounded-full">{tag}</span>
            ))}
          </div>
          <div className="flex flex-col sm:flex-row gap-4">
            <a href="mailto:neeljshah22@gmail.com" className="flex items-center gap-3 px-5 py-3 bg-[#3b82f6] text-white rounded-lg hover:bg-blue-500 transition-colors font-medium">
              <Mail size={18}/> neeljshah22@gmail.com
            </a>
            <a href="https://linkedin.com/in/neeljshah22" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 px-5 py-3 border border-[#1f1f2e] text-[#9999a8] rounded-lg hover:text-[#e7e7ee] hover:border-[#3b82f6] transition-colors">
              <LinkedInIcon /> LinkedIn
            </a>
            <a href="https://github.com/neeljshah" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 px-5 py-3 border border-[#1f1f2e] text-[#9999a8] rounded-lg hover:text-[#e7e7ee] hover:border-[#3b82f6] transition-colors">
              <GitHubIcon /> GitHub
            </a>
          </div>
        </motion.div>
      </div>
      <div className="max-w-6xl mx-auto px-6 mt-24 pt-8 border-t border-[#1f1f2e]">
        <p className="font-mono text-xs text-[#9999a8] opacity-40">© 2026 Neel Shah · Built with Next.js · April 2026</p>
      </div>
    </section>
  )
}
