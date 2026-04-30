'use client'
import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

interface CounterProps { target: number; label: string; prefix?: string; suffix?: string; decimals?: number }

function Counter({ target, label, prefix = '', suffix = '', decimals = 0 }: CounterProps) {
  const [val, setVal] = useState(0)
  const ref = useRef<HTMLDivElement>(null)
  const started = useRef(false)

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !started.current) {
        started.current = true
        const start = Date.now()
        const dur = 1200
        const tick = () => {
          const p = Math.min((Date.now() - start) / dur, 1)
          const ease = 1 - Math.pow(1 - p, 3)
          setVal(target * ease)
          if (p < 1) requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }
    }, { threshold: 0.1 })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [target])

  const display = decimals > 0 ? val.toFixed(decimals) : Math.floor(val).toLocaleString()

  return (
    <div ref={ref} className="text-center">
      <div className="font-mono text-3xl font-bold text-[#e7e7ee] tabular-nums">
        {prefix}{display}{suffix}
      </div>
      <div className="text-xs text-[#9999a8] mt-1 uppercase tracking-widest">{label}</div>
    </div>
  )
}

const FADE = { hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0 } }

export default function Hero() {
  return (
    <section className="relative min-h-screen flex flex-col justify-center py-24 overflow-hidden">
      {/* dot grid */}
      <div className="absolute inset-0 pointer-events-none" style={{
        backgroundImage: 'radial-gradient(circle, #3b82f6 1px, transparent 1px)',
        backgroundSize: '32px 32px',
        opacity: 0.04,
      }} />
      <div className="relative max-w-6xl mx-auto px-6 w-full">
        <motion.div variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6 }}>
          <p className="font-mono text-xs text-[#3b82f6] tracking-[0.25em] uppercase mb-6">Quantitative Researcher</p>
        </motion.div>
        <motion.h1
          variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6, delay: 0.1 }}
          className="text-6xl md:text-7xl font-bold text-[#e7e7ee] leading-none tracking-tight mb-6"
        >
          Neel Shah
        </motion.h1>
        <motion.div
          variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6, delay: 0.2 }}
          className="max-w-2xl mb-12"
        >
          <p className="text-lg text-[#9999a8] leading-relaxed">
            Public sports markets price off box-score aggregates. I extract defender proximity,
            floor spacing, and fatigue from broadcast video — signals that don&apos;t exist in any
            public dataset — and benchmark fills against Pinnacle&apos;s closing line.
          </p>
        </motion.div>
        <motion.div
          variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6, delay: 0.3 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12 max-w-2xl"
        >
          <Counter target={75} label="ML Models" suffix="+" />
          <Counter target={960} label="Passing Tests" suffix="+" />
          <Counter target={14} label="CLV bps/bet" prefix="+" />
          <Counter target={312} label="Settled Picks" />
        </motion.div>
        <motion.div
          variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6, delay: 0.4 }}
          className="flex flex-wrap gap-3 mb-16"
        >
          <a href="#architecture" className="px-5 py-2.5 bg-[#3b82f6] text-white text-sm font-medium rounded hover:bg-blue-500 transition-colors">
            View System →
          </a>
          <a href="mailto:neeljshah22@gmail.com" className="px-5 py-2.5 border border-[#1f1f2e] text-[#9999a8] text-sm font-medium rounded hover:text-[#e7e7ee] hover:border-[#3b82f6] transition-colors">
            neeljshah22@gmail.com
          </a>
        </motion.div>
        <motion.p
          variants={FADE} initial="hidden" animate="show" transition={{ duration: 0.6, delay: 0.5 }}
          className="font-mono text-xs text-[#9999a8] opacity-40"
        >
          Last updated: April 2026
        </motion.p>
      </div>
    </section>
  )
}
