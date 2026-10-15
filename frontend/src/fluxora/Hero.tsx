import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { ArrowRight, Globe } from './icons'
import './Hero.css'

const bars = [34, 52, 44, 70, 88]

type Props={deckCount:number;balance:number|null;name:string;onCreate:()=>void;nav:(path:string)=>void};
export default function Hero({deckCount,balance,name,onCreate,nav}:Props) {
  const stats=[{value:String(deckCount).padStart(2,'0'),label:'Your presentations'},{value:balance===null?'—':String(balance),label:'Available credits'}];
  const videoRef = useRef<HTMLVideoElement>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    // Some browsers block autoplay until the element is explicitly nudged.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      video.pause()
      setReady(true)
    } else {
      const play = video.play()
      if (play?.catch) play.catch(() => {})
    }
  }, [])

  return (
    <section className="fx-hero">
      <div className="fx-hero__media">
        <video
          ref={videoRef}
          className={`fx-hero__video ${ready ? 'is-ready' : ''}`}
          src="/hero-loop.mp4"
          muted
          loop
          playsInline
          preload="auto"
          aria-hidden="true"
          onCanPlay={() => setReady(true)}
          onError={() => setReady(false)}
        />
        <div className="fx-hero__scrim" aria-hidden="true" />
        <div className="fx-hero__rules" aria-hidden="true">
          <span /><span /><span />
        </div>
      </div>

      <div className="fx-hero__inner">
        <div className="fx-hero__lead">
          <p className="fx-hero__note">
            <Globe className="fx-hero__note-icon" />
            <span>Welcome back, {name}.<br />Your next chapter starts here.</span>
          </p>

          <h1 className="fx-hero__title">
            Big ideas.<br />
            Crafted by You.<br />
            Made to <em>Move.</em>
          </h1>

          <p className="fx-hero__sub">
            From a first spark to your final slide. Create, refine and present
            your best ideas in one beautifully connected studio.
          </p>

          <div className="fx-hero__cta">
            <button className="fx-btn fx-btn--flame fx-hero__go" onClick={onCreate}>
              Create a presentation
              <span className="fx-hero__go-dot" aria-hidden="true"><ArrowRight /></span>
            </button>

            <div className="fx-hero__proof">
              <div className="fx-hero__faces" aria-hidden="true">
                <i style={{ '--a': '#ff7a3d', '--b': '#ffb27a' } as CSSProperties} />
                <i style={{ '--a': '#6f4bd8', '--b': '#a98cff' } as CSSProperties} />
                <i style={{ '--a': '#1f9ea8', '--b': '#63d6df' } as CSSProperties} />
                <i style={{ '--a': '#d8434b', '--b': '#ff8a8f' } as CSSProperties} />
              </div>
              <span className="fx-hero__proof-text">
                <strong>Your personal studio</strong>
                Ideas → impact
              </span>
            </div>
          </div>

          <ul className="fx-hero__stats">
            {stats.map((stat) => (
              <li key={stat.label} className="fx-stat">
                <span className="fx-stat__mark" aria-hidden="true">*</span>
                <span className="fx-stat__value">{stat.value}</span>
                <span className="fx-stat__label">{stat.label}</span>
                <span className="fx-stat__rule" aria-hidden="true" />
              </li>
            ))}
          </ul>
        </div>

        <aside className="fx-hero__ghost" aria-hidden="true">
          <div className="fx-ghost__row">
            <div className="fx-ghost__bars">
              {bars.map((h, i) => (
                <span key={i} style={{ height: `${h}%` }} />
              ))}
            </div>
            <p className="fx-ghost__kpi"><strong>∞</strong>Ideas worth<br />sharing</p>
          </div>
          <h2 className="fx-ghost__title">Make Your Next Chapter</h2>
          <p className="fx-ghost__copy">
            Every thought has a story. Find yours, shape it, and bring it to life.
          </p>
        </aside>
      </div>

      <div className="fx-hero__foot">
        <span className="fx-hero__watermark" aria-hidden="true">AIM</span>
        <div className="fx-hero__partners">
          <span className="fx-hero__partners-label">YOUR STUDIO, AT YOUR FINGERTIPS</span>
          <nav className="featureDock" aria-label="Studio features">
            {[{label:'AI Create',path:'/create'},{label:'Projects',path:'/projects'},{label:'My decks',path:'#library'},{label:'History',path:'/history'},{label:'Credits',path:'/credits'}].map(feature=><button key={feature.label} onClick={()=>feature.path==='#library'?document.getElementById('library')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}):nav(feature.path)}>{feature.label}<ArrowRight/></button>)}
          </nav>
        </div>
      </div>
    </section>
  )
}
