import {useEffect,useState} from 'react';
import {request,type User} from './api';
import {ThemePicker} from './appearance';
import {Logo,Menu,Close,ArrowRight} from './fluxora/icons';
import Hero from './fluxora/Hero';
import Workspace from './Workspace';
import './fluxora/base.css';
import './fluxora/Navbar.css';
import './fluxora/integration.css';
type Deck={id:string;title:string;theme:string;version:number;slides:unknown[]};
type Props={user:User|null;decks:Deck[];nav:(path:string)=>void;onCreate:(prompt:string)=>void;onLogout:()=>void};
export default function FluxoraHome({user,decks,nav,onCreate,onLogout}:Props){
 const[open,setOpen]=useState(false);const[balance,setBalance]=useState<number|null>(null);
 useEffect(()=>{let alive=true;request('/credits').then(wallet=>{if(alive)setBalance(wallet.balance)}).catch(()=>{});return()=>{alive=false}},[]);
 useEffect(()=>{if(!open)return;const close=(event:KeyboardEvent)=>{if(event.key==='Escape')setOpen(false)};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[open]);
 const links=[{label:'Create',path:'/create'},{label:'Projects',path:'/projects'},{label:'My decks',path:'#library'},{label:'History',path:'/history'},{label:'Credits',path:'/credits'}];
 const go=(path:string)=>{setOpen(false);if(path==='#library')document.getElementById('library')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});else nav(path)};
 return <div className="fluxora"><a className="fx-skip" href="#fluxora-main">Skip to content</a><header className="fx-nav"><button className="fx-nav__brand" onClick={()=>nav('/')} aria-label="Back to theme ring"><Logo className="fx-nav__logo"/><span>PPTX.AI</span></button><nav className="fx-nav__pill" aria-label="Primary"><ul>{links.map(link=><li key={link.label}><button onClick={()=>go(link.path)}>{link.label}</button></li>)}</ul></nav><div className="fx-nav__actions"><ThemePicker/><button className="fx-btn fx-btn--light fx-nav__cta" onClick={onLogout}>Sign out</button><button className="fx-nav__burger" type="button" aria-label={open?'Close menu':'Open menu'} aria-expanded={open} aria-controls="fluxora-menu" onClick={()=>setOpen(!open)}>{open?<Close/>:<Menu/>}</button></div>{open&&<div id="fluxora-menu" className="fx-nav__sheet"><ul>{links.map(link=><li key={link.label}><button onClick={()=>go(link.path)}>{link.label}<ArrowRight/></button></li>)}</ul><button className="fx-btn fx-btn--flame" onClick={onLogout}>Sign out</button></div>}</header><main id="fluxora-main"><Hero deckCount={decks.length} balance={balance} name={user?.name?.split(' ')[0]||'creator'} onCreate={()=>onCreate('')} nav={go}/><section id="library" className="fluxora-library" aria-label="Your presentation library"><Workspace user={user} decks={decks} nav={nav} onCreate={onCreate}/></section></main><div className="fluxoraFooter"><span>PPTX.AI — YOUR NEXT CHAPTER</span><button onClick={()=>nav('/')}>Explore the theme ring <ArrowRight/></button></div></div>
}
