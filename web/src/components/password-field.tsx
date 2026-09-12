"use client";

import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import type { Lang } from "@/lib/types";

export function PasswordField({lang,value,onChange,newPassword=true,label}:{lang:Lang;value:string;onChange:(value:string)=>void;newPassword?:boolean;label?:string}) {
  const [visible,setVisible]=useState(false);
  const id=useId(),fa=lang==="fa";
  return <div className="password-field">
    <label htmlFor={id}>{label??(fa?"رمز عبور":"Password")}</label>
    <div className="password-control">
      <input id={id} type={visible?"text":"password"} required minLength={newPassword?8:1} maxLength={128}
        pattern={newPassword?"(?=.*[A-Z])(?=.*[0-9])(?=.*[^\\w\\s]).{8,128}":undefined}
        autoComplete={newPassword?"new-password":"current-password"} autoCapitalize="none" spellCheck={false} dir="ltr"
        aria-describedby={newPassword?id+"-hint":undefined} value={value} onChange={e=>onChange(e.target.value)}/>
      <button type="button" className="icon-button" aria-label={fa?(visible?"پنهان کردن رمز":"نمایش رمز"):(visible?"Hide password":"Show password")} aria-pressed={visible} onClick={()=>setVisible(!visible)}>{visible?<EyeOff/>:<Eye/>}</button>
    </div>
    {newPassword&&<small id={id+"-hint"}>{fa?"۸ تا ۱۲۸ نویسه، حداقل یک حرف بزرگ انگلیسی، یک عدد و یک نماد مثل !":"8–128 characters, including an uppercase letter, a number and a symbol such as !"}</small>}
  </div>;
}
