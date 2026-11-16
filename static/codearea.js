// Код жазуға ыңғайлы textarea: Tab = 4 бос орын, Enter кезінде шегініс сақталады, ":" кейін шегініс қосылады.
function enhanceCodeArea(ta, onRun){
  ta.setAttribute('spellcheck','false');
  ta.addEventListener('keydown', e=>{
    const s=ta.selectionStart, en=ta.selectionEnd, v=ta.value;
    if(e.key==='Tab'){
      e.preventDefault();
      const ls=v.lastIndexOf('\n',s-1)+1;
      if(s!==en && v.slice(s,en).includes('\n')){
        const block=v.slice(ls,en);
        const nb=e.shiftKey? block.replace(/^ {1,4}/gm,'') : block.replace(/^/gm,'    ');
        ta.value=v.slice(0,ls)+nb+v.slice(en); ta.selectionStart=ls; ta.selectionEnd=ls+nb.length;
      } else if(e.shiftKey){
        const m=v.slice(ls).match(/^ {1,4}/); if(m){ta.value=v.slice(0,ls)+v.slice(ls+m[0].length); ta.selectionStart=ta.selectionEnd=Math.max(ls,s-m[0].length);}
      } else { ta.value=v.slice(0,s)+'    '+v.slice(en); ta.selectionStart=ta.selectionEnd=s+4; }
    } else if(e.key==='Enter' && !e.ctrlKey && !e.metaKey){
      e.preventDefault();
      const ls=v.lastIndexOf('\n',s-1)+1, line=v.slice(ls,s);
      let ind=(line.match(/^\s*/)||[''])[0];
      if(/:\s*$/.test(line)) ind+='    ';
      ta.value=v.slice(0,s)+'\n'+ind+v.slice(en); ta.selectionStart=ta.selectionEnd=s+1+ind.length;
    } else if(e.key==='Enter' && (e.ctrlKey||e.metaKey) && onRun){ e.preventDefault(); onRun(); }
    else if(e.key==='Backspace' && s===en){
      const ls=v.lastIndexOf('\n',s-1)+1, before=v.slice(ls,s);
      if(before.length && /^ +$/.test(before) && before.length%4===0){ e.preventDefault(); ta.value=v.slice(0,s-4)+v.slice(s); ta.selectionStart=ta.selectionEnd=s-4; }
    }
  });
}
