import {ArrowRight,ArrowUpRight,Sparkles} from 'lucide-react';
import {THEMES,ThemePicker,useAppearance} from './appearance';
import {WorksWheel} from './components/ui/works-wheel';
import './entry.css';
export default function EntryPage({authenticated,navigate,onCreate}:{authenticated:boolean;navigate:(path:string)=>void;onCreate:()=>void}){
 const {theme,setTheme}=useAppearance();
 const choose=(index:number)=>setTheme(THEMES[index].id);
 return <main className="entryPage">
  <div className="entryScene" aria-hidden="true"/><div className="entryGrain" aria-hidden="true"/>
  <header className="entryNav"><a className="entryBrand" href="/" aria-label="PPTX.AI home"><Sparkles size={22}/> PPTX<span>.AI</span></a><ThemePicker/><div className="entryNavActions"><button onClick={()=>navigate(authenticated?'/app':'/login')}>{authenticated?'My studio':'Log in'} <ArrowUpRight size={15}/></button><button className="entryPrimary" onClick={()=>navigate(authenticated?'/app':'/signup')}>{authenticated?'Open studio':'Get started'} <ArrowRight size={16}/></button></div></header>
  <section className="entryIntro"><span className="entryEyebrow"><i/> ONE STUDIO. EIGHT DIFFERENT WORLDS.</span><h1>Your ideas.<br/><em>Your atmosphere.</em></h1><p>Choose a world that feels like you.<br/>Turn your next spark into a story worth sharing.</p></section>
  <div className="entryWheel"><WorksWheel items={THEMES.map(item=>({title:item.name,image:item.image,fallbackImage:item.fallbackImage,href:'#'+item.id}))} label="Choose your atmosphere" action="Apply theme" onActivate={(_,index)=>choose(index)} onChoose={choose}/></div>
  <section className="entrySelection" aria-label="Choose your screen theme"><div className="entrySelectionHeading"><span>01 — CHOOSE YOUR WORLD</span><span>SCROLL · DRAG · EXPLORE</span></div><div className="entrySwatches">{THEMES.map(item=><button key={item.id} className={theme.id===item.id?'selected':''} aria-pressed={theme.id===item.id} onClick={()=>setTheme(item.id)}><span className={'entrySwatch entrySwatch--'+item.id}/>{item.name}<i/></button>)}</div><div className="entrySelectionFoot"><div><strong>{theme.name}</strong><span>{theme.description}</span></div><button onClick={onCreate}>Create in this world <ArrowRight size={17}/></button></div></section>
  <footer className="entryFoot"><span>PPTX.AI / MADE FOR YOUR NEXT BIG IDEA</span><span>YOUR WORLD. YOUR STORY. <Sparkles size={12}/></span></footer>
 </main>
}
