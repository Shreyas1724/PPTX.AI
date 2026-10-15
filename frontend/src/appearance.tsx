import { createContext, useContext, useLayoutEffect, useState, type ReactNode } from 'react';

export type ThemeId = 'nature'|'ocean'|'space'|'sunset'|'aurora'|'minimal'|'cyberpunk'|'rose';
export type AppearanceTheme = {id:ThemeId;name:string;description:string;image:string;fallbackImage:string;accent:string;bg:string;panel:string;strong:string;ink:string;muted:string;accentInk:string;glow:string;font:string;displayFont:string;radius:string;scheme:'dark'|'light'};
const sans = "'DM Sans', sans-serif";
const display = "'Space Grotesk', sans-serif";
export const THEMES:AppearanceTheme[] = [
 {id:'nature',name:'Nature',description:'Forest light. A fresh perspective.',accent:'#bde2a3',bg:'#091b14',panel:'#102a20',strong:'#18392b',ink:'#f3f5e9',muted:'#bacbbd',accentInk:'#142315',glow:'#60865a',font:sans,displayFont:"'Instrument Serif', Georgia, serif",radius:'22px',scheme:'dark'},
 {id:'ocean',name:'Ocean',description:'Deep blues. Room to explore.',accent:'#8de1ee',bg:'#071923',panel:'#102b3b',strong:'#173b4d',ink:'#eefaff',muted:'#accbd7',accentInk:'#072931',glow:'#247f9c',font:sans,displayFont:display,radius:'18px',scheme:'dark'},
 {id:'space',name:'Space',description:'Big ideas. Infinite possibility.',accent:'#cbb5fa',bg:'#0b0b15',panel:'#191525',strong:'#292039',ink:'#f5f1fb',muted:'#bdb2cf',accentInk:'#211333',glow:'#7752bd',font:sans,displayFont:display,radius:'18px',scheme:'dark'},
 {id:'sunset',name:'Sunset',description:'Golden hour, all day long.',accent:'#ff8a1f',bg:'#120400',panel:'#2a0b02',strong:'#4a1c0b',ink:'#fff3e7',muted:'#dbb7aa',accentInk:'#3b1b15',glow:'#ba6658',font:sans,displayFont:"'Instrument Serif', Georgia, serif",radius:'24px',scheme:'dark'},
 {id:'aurora',name:'Aurora',description:'A little wonder in every detail.',accent:'#a3efcc',bg:'#0c1820',panel:'#142b35',strong:'#213c47',ink:'#effcf9',muted:'#b1d0cd',accentInk:'#112e27',glow:'#548e8d',font:sans,displayFont:display,radius:'22px',scheme:'dark'},
 {id:'minimal',name:'Minimal',description:'Less noise. More meaning.',accent:'#333a30',bg:'#eeece5',panel:'#faf9f4',strong:'#e2e3d8',ink:'#242a23',muted:'#606658',accentInk:'#fafaf2',glow:'#a7b19c',font:sans,displayFont:display,radius:'8px',scheme:'light'},
 {id:'cyberpunk',name:'Cyberpunk',description:'Electric color. Unfiltered ambition.',accent:'#e7fa91',bg:'#111020',panel:'#211931',strong:'#31213e',ink:'#faf5ff',muted:'#c4b4d2',accentInk:'#252b12',glow:'#b343aa',font:sans,displayFont:display,radius:'6px',scheme:'dark'},
 {id:'rose',name:'Rose',description:'Soft edges. A bold point of view.',accent:'#f1b7ca',bg:'#24171f',panel:'#38232f',strong:'#503341',ink:'#fff3f7',muted:'#d6b9c7',accentInk:'#3b1c2b',glow:'#ae6686',font:sans,displayFont:"'Instrument Serif', Georgia, serif",radius:'26px',scheme:'dark'},
].map(theme=>({...theme,image:`/themes/${theme.id}.jpg`,fallbackImage:`/themes/${theme.id}.svg`})) as AppearanceTheme[];

const STORAGE_KEY='pptx-appearance';
const getTheme=(id:string|null)=>THEMES.find(theme=>theme.id===id)??THEMES[3];
const AppearanceContext=createContext<{theme:AppearanceTheme;setTheme:(id:ThemeId)=>void}|null>(null);
export function AppearanceProvider({children}:{children:ReactNode}) {
 const [theme,setCurrent]=useState<AppearanceTheme>(()=>{try{return getTheme(localStorage.getItem(STORAGE_KEY))}catch{return THEMES[3]}});
 useLayoutEffect(()=>{
  const root=document.documentElement;
  root.dataset.appearance=theme.id;root.dataset.colorScheme=theme.scheme;
  const tokens:Record<string,string>={bg:theme.bg,panel:theme.panel,'panel-strong':theme.strong,ink:theme.ink,muted:theme.muted,accent:theme.accent,'accent-ink':theme.accentInk,border:`color-mix(in srgb, ${theme.ink} 17%, transparent)`,glow:theme.glow,font:theme.font,'display-font':theme.displayFont,radius:theme.radius,scene:`url("${theme.image}"),url("${theme.fallbackImage}")`};
  for(const [key,value] of Object.entries(tokens))root.style.setProperty('--app-'+key,value);
  root.style.colorScheme=theme.scheme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme.bg);
  try{localStorage.setItem(STORAGE_KEY,theme.id)}catch{/* Selection still works when storage is unavailable. */}
 },[theme]);
 useLayoutEffect(()=>{const sync=(event:StorageEvent)=>{if(event.key===STORAGE_KEY)setCurrent(getTheme(event.newValue))};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync)},[]);
 return <AppearanceContext.Provider value={{theme,setTheme:id=>setCurrent(getTheme(id))}}>{children}</AppearanceContext.Provider>;
}
export function useAppearance(){const context=useContext(AppearanceContext);if(!context)throw new Error('AppearanceProvider is required');return context}
export function ThemePicker(){const {theme,setTheme}=useAppearance();return <label className="appearance-picker"><span className="appearance-picker__dot" aria-hidden="true"/><span className="appearance-picker__label">Appearance</span><select aria-label="Screen theme" value={theme.id} onChange={event=>setTheme(event.target.value as ThemeId)}>{THEMES.map(option=><option value={option.id} key={option.id}>{option.name}</option>)}</select></label>}
