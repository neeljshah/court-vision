import Hero from './components/Hero'
import Architecture from './components/Architecture'
import CVMoat from './components/CVMoat'
import LiveDemo from './components/LiveDemo'
import ModelPerformance from './components/ModelPerformance'
import Portfolio from './components/Portfolio'
import EngineeringDepth from './components/EngineeringDepth'
import OtherWork from './components/OtherWork'
import Principles from './components/Principles'
import Stack from './components/Stack'
import Contact from './components/Contact'

export default function Page() {
  return (
    <main>
      <Hero />
      <Architecture />
      <CVMoat />
      <LiveDemo />
      <ModelPerformance />
      <Portfolio />
      <EngineeringDepth />
      <OtherWork />
      <Principles />
      <Stack />
      <Contact />
    </main>
  )
}
