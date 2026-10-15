export const API=(import.meta.env.VITE_API_URL||'/api/v1').replace(/\/$/,'');
export class ApiError extends Error {
 constructor(message:string,public status:number){super(message);this.name='ApiError'}
}
export function websocketUrl(path:string){
 const url=new URL(API+path,location.origin);
 url.protocol=url.protocol==='https:'?'wss:':'ws:';
 return url.toString();
}
function csrfToken(){
 const value=document.cookie.split(';').map(cookie=>cookie.trim()).find(cookie=>cookie.startsWith('pptx_csrf='))?.slice('pptx_csrf='.length)||'';
 try{return decodeURIComponent(value)}catch{return ''}
}
export async function request(path:string,method='GET',body?:unknown,extraHeaders:Record<string,string>={}){
 const res=await fetch(API+path,{method,credentials:'include',headers:{...(body instanceof FormData?{}:{'Content-Type':'application/json'}),...(method!=='GET'?{'X-CSRF-Token':csrfToken()} : {}),...extraHeaders},body:body instanceof FormData?body:body!==undefined?JSON.stringify(body):undefined});
 if(!res.ok){let message='Something went wrong. Please try again.';try{const data=await res.json();if(Array.isArray(data.detail))message=data.detail.map((x:{msg?:string})=>String(x.msg||'Invalid value').replace('Value error, ','')).join('. ');else if(typeof data.detail==='string')message=data.detail}catch{}throw new ApiError(message,res.status)}
 return res.headers.get('content-type')?.includes('application/json')?res.json():res;
}
export type User={id:string;name:string;email:string;mobile:string;role:string;credits:number;email_verified:boolean;mobile_verified:boolean};
