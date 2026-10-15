import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {Pause, Play} from 'lucide-react';
import './feature-background.css';

export type FeatureScene = 'create'|'projects'|'credits'|'decks'|'history';

const SCENES: Record<FeatureScene, {image:string; color:string; secondary:string; label:string}> = {
  create: {image:'space', color:'#bd96ff', secondary:'#75d8ff', label:'Creative cosmos'},
  projects: {image:'nature', color:'#a6e7c0', secondary:'#70cde1', label:'Living ideas'},
  credits: {image:'sunset', color:'#ffc48a', secondary:'#ff8c82', label:'Golden possibilities'},
  decks: {image:'ocean', color:'#8be5f3', secondary:'#b5afff', label:'Ocean of stories'},
  history: {image:'aurora', color:'#9ff4dc', secondary:'#c3acff', label:'Traces of light'},
};
const MOTION_KEY = 'pptx-background-motion';
type Particle = {x:number; y:number; z:number; radius:number; phase:number};
type Ripple = {x:number; y:number; born:number};

/** Decorative only: all pointer listeners are passive and leave the workspace usable. */
export default function FeatureBackground({variant, className=''}:{variant:FeatureScene; className?:string}) {
  const scene = SCENES[variant];
  const rootRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [enabled, setEnabled] = useState(() => {
    try {return localStorage.getItem(MOTION_KEY) !== 'off'} catch {return true}
  });
  const [reduced, setReduced] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || !document.hidden);
  const animated = enabled && !reduced && visible;

  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const changeMotion = () => setReduced(media.matches);
    const changeVisibility = () => setVisible(!document.hidden);
    media.addEventListener('change', changeMotion);
    document.addEventListener('visibilitychange', changeVisibility);
    return () => {
      media.removeEventListener('change', changeMotion);
      document.removeEventListener('visibilitychange', changeVisibility);
    };
  }, []);

  useEffect(() => {
    const root = rootRef.current;
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!root || !canvas || !context) return;
    let width = 1, height = 1, frame = 0, elapsed = 0, previous = 0;
    let pointerX = 0, pointerY = 0, smoothX = 0, smoothY = 0;
    let particles:Particle[] = [];
    const ripples:Ripple[] = [];
    const resize = () => {
      const bounds = root.getBoundingClientRect();
      width = Math.max(1, bounds.width); height = Math.max(1, bounds.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(90, Math.max(30, Math.floor(width * height / 19000)));
      particles = Array.from({length:count}, (_,i) => ({
        x:((i * .61803398875) % 1) * width,
        y:((i * .75487766625) % 1) * height,
        z:.3 + (i % 7) / 10, radius:.6 + (i % 4) * .4, phase:i * 1.7,
      }));
      draw();
    };
    const draw = () => {
      context.clearRect(0,0,width,height);
      smoothX += (pointerX - smoothX) * .035;
      smoothY += (pointerY - smoothY) * .035;
      root.style.setProperty('--scene-x', `${smoothX * 18}px`);
      root.style.setProperty('--scene-y', `${smoothY * 13}px`);
      root.style.setProperty('--scene-tilt-x', `${-smoothY * 7}deg`);
      root.style.setProperty('--scene-tilt-y', `${smoothX * 9}deg`);
      context.fillStyle = scene.color;
      for (const point of particles) {
        const x = (point.x + Math.sin(elapsed * .12 + point.phase) * 20 + smoothX * point.z * 22 + width) % width;
        const y = ((point.y - elapsed * (4 + point.z * 6)) % height + height) % height;
        const twinkle = .33 + (Math.sin(elapsed * .6 + point.phase) + 1) * .21;
        context.globalAlpha = twinkle * point.z;
        context.beginPath();context.arc(x,y,point.radius,0,Math.PI*2);context.fill();
        if (point.z > .8) {
          context.globalAlpha = .04;
          context.beginPath();context.arc(x,y,point.radius * 5,0,Math.PI*2);context.fill();
        }
      }
      context.globalAlpha = 1;
      for (let i=ripples.length-1; i>=0; i--) {
        const age = elapsed-ripples[i].born;
        if (age > 2.4) {ripples.splice(i,1);continue}
        const ripple = ripples[i];
        context.globalAlpha = (1-age/2.4)*.3;
        context.strokeStyle = scene.color;context.lineWidth = 1;
        context.beginPath();context.ellipse(ripple.x,ripple.y,25+age*110,12+age*55,-.25,0,Math.PI*2);context.stroke();
      }
      context.globalAlpha = 1;
    };
    const tick = (time:number) => {
      if (previous) elapsed += Math.min((time-previous)/1000,.05);
      previous = time;draw();frame = requestAnimationFrame(tick);
    };
    const move = (event:PointerEvent) => {
      if(event.pointerType === 'touch')return;
      const bounds = root.getBoundingClientRect();
      pointerX = Math.max(-1,Math.min(1,(event.clientX-bounds.left)/width*2-1));
      pointerY = Math.max(-1,Math.min(1,(event.clientY-bounds.top)/height*2-1));
    };
    const leave = () => {pointerX=0;pointerY=0};
    const ripple = (event:PointerEvent) => {
      const bounds = root.getBoundingClientRect();
      if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)return;
      if((event.target as Element | null)?.closest('button,input,textarea,select,a,[role="dialog"]'))return;
      if(ripples.length>=5)ripples.shift();
      ripples.push({x:event.clientX-bounds.left,y:event.clientY-bounds.top,born:elapsed});
    };
    const observer = new ResizeObserver(resize);observer.observe(root);resize();
    if (animated) {
      frame = requestAnimationFrame(tick);
      window.addEventListener('pointermove',move,{passive:true});
      window.addEventListener('pointerdown',ripple,{passive:true});
      document.documentElement.addEventListener('pointerleave',leave,{passive:true});
    }
    return () => {
      cancelAnimationFrame(frame);observer.disconnect();
      window.removeEventListener('pointermove',move);window.removeEventListener('pointerdown',ripple);
      document.documentElement.removeEventListener('pointerleave',leave);
      root.style.setProperty('--scene-x','0px');root.style.setProperty('--scene-y','0px');
      root.style.setProperty('--scene-tilt-x','0deg');root.style.setProperty('--scene-tilt-y','0deg');
    };
  }, [animated, scene]);

  const toggleMotion = () => {
    const next = !enabled;setEnabled(next);
    try {localStorage.setItem(MOTION_KEY,next?'on':'off')} catch {/* Preference still works in this tab. */}
  };
  const style = {'--scene-image':`url('/themes/${scene.image}.jpg')`,'--scene-color':scene.color,'--scene-secondary':scene.secondary} as CSSProperties;
  return <>
    <div ref={rootRef} className={`featureBackground featureBackground--${variant} ${className}`} style={style} data-motion={animated?'running':'paused'} aria-hidden="true">
      <div className="featureBackground__photo"/>
      <div className="featureBackground__veil"/>
      <div className="featureBackground__nebula featureBackground__nebula--one"/>
      <div className="featureBackground__nebula featureBackground__nebula--two"/>
      <div className="featureBackground__horizon"/>
      <div className="featureBackground__sculpture">
        <div className="featureBackground__ring featureBackground__ring--one"/>
        <div className="featureBackground__ring featureBackground__ring--two"/>
        <div className="featureBackground__ring featureBackground__ring--three"/>
        <div className="featureBackground__orb"><div/></div>
        <div className="featureBackground__satellite featureBackground__satellite--one"/>
        <div className="featureBackground__satellite featureBackground__satellite--two"/>
      </div>
      <div className="featureBackground__caustics"/>
      <canvas ref={canvasRef} className="featureBackground__particles"/>
      <div className="featureBackground__grain"/>
    </div>
    <button className="featureMotionToggle" type="button" onClick={toggleMotion} disabled={reduced} aria-pressed={enabled&&!reduced} aria-label={reduced?'Background motion reduced by system preference':enabled?'Pause animated background':'Play animated background'} title={scene.label}>
      {enabled&&!reduced?<Pause size={12}/>:<Play size={12}/>}<span>{reduced?'Reduced motion':enabled?'Pause motion':'Resume motion'}</span>
    </button>
  </>;
}
