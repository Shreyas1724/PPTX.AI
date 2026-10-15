export const API=import.meta.env.VITE_API_URL||'/api/v1';
export async function request(path:string,method='GET',body?:unknown,extraHeaders:Record<string,string>={}){
 const res=await fetch(API+path,{method,credentials:'include',headers:{...(body instanceof FormData?{}:{'Content-Type':'application/json'}),...(method!=='GET'?{'X-CSRF-Token':decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('pptx_csrf='))?.split('=')[1]||'')} : {}),...extraHeaders},body:body instanceof FormData?body:body?JSON.stringify(body):undefined});
 if(!res.ok){let message='Something went wrong. Please try again.';try{const data=await res.json();message=Array.isArray(data.detail)?data.detail.map((x:{msg:string})=>x.msg.replace('Value error, ','')).join('. '):data.detail||message}catch{}throw new Error(message)}
 return res.headers.get('content-type')?.includes('application/json')?res.json():res;
}
export type User={id:string;name:string;email:string;mobile:string;role:string;credits:number;email_verified:boolean;mobile_verified:boolean};
