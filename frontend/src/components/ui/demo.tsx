"use client";
import {WorksWheel,type WorksWheelItem} from '@/components/ui/works-wheel';
const ART=(id:string)=>`https://images.unsplash.com/${id}?auto=format&fit=crop&w=1000&q=85`;
const WORKS:WorksWheelItem[]=[
 {title:'A new perspective',image:ART('photo-1464822759023-fed622ff2c3b'),href:'/create'},
 {title:'The next frontier',image:ART('photo-1446776811953-b23d57bd21aa'),href:'/create'},
 {title:'Ideas in motion',image:ART('photo-1518837695005-2083093ee35b'),href:'/create'},
 {title:'Built for tomorrow',image:ART('photo-1486406146926-c627a92ad1ab'),href:'/create'},
 {title:'Beyond the ordinary',image:ART('photo-1470770841072-f978cf4d019e'),href:'/create'},
 {title:'A brighter story',image:ART('photo-1500534623283-312aade485b7'),href:'/create'},
 {title:'Make your mark',image:ART('photo-1497250681960-ef046c08a56e'),href:'/create'},
 {title:'Find your direction',image:ART('photo-1472396961693-142e6e269027'),href:'/create'},
 {title:'Endless possibility',image:ART('photo-1469474968028-56623f02e42e'),href:'/create'},
];
export default function WorksWheelDemo(){return <div className="wheelDemo bg-background text-foreground w-full"><WorksWheel items={WORKS} label="Stories in orbit" action="Create"/></div>}
