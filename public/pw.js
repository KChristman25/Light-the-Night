(function(){
  const KEY='ltn_pw';
  if(sessionStorage.getItem(KEY)==='ok') return;
  function mount(){
    if(document.getElementById('_pwGate')) return;
    const g=document.createElement('div');
    g.id='_pwGate';
    g.style.cssText='position:fixed;inset:0;z-index:999999;background:#231207;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:24px;';
    g.innerHTML=
      '<div style="font-family:\'Press Start 2P\',monospace;font-size:clamp(12px,3vw,20px);color:#e8a000;text-shadow:2px 2px 0 #000;text-align:center;line-height:1.8">LIGHT THE NIGHT</div>'+
      '<input id="_pwIn" type="password" placeholder="Password" autocomplete="off" inputmode="text" '+
        'style="font-size:20px;padding:14px 20px;background:#3a1f0a;color:#fff;border:3px solid #e8a000;border-radius:4px;text-align:center;outline:none;width:100%;max-width:300px;letter-spacing:0.15em;font-family:\'Press Start 2P\',monospace;">'+
      '<div id="_pwErr" style="font-family:\'Press Start 2P\',monospace;font-size:9px;color:#ff8080;min-height:14px;text-align:center;"></div>'+
      '<button id="_pwBtn" style="font-family:\'Press Start 2P\',monospace;font-size:11px;padding:14px 32px;background:#e52521;color:#fff;border:3px solid #e8a000;border-radius:4px;cursor:pointer;width:100%;max-width:300px;box-shadow:4px 4px 0 #e8a000;">ENTER &#9658;</button>';
    document.body.appendChild(g);
    function attempt(){
      const v=(document.getElementById('_pwIn').value||'').trim().toUpperCase();
      if(v==='SCFBC'){
        sessionStorage.setItem(KEY,'ok');
        g.remove();
      } else {
        document.getElementById('_pwErr').textContent='Wrong password';
        document.getElementById('_pwIn').value='';
        setTimeout(function(){ var i=document.getElementById('_pwIn'); if(i) i.focus(); },50);
      }
    }
    document.getElementById('_pwBtn').addEventListener('click',attempt);
    document.getElementById('_pwIn').addEventListener('keydown',function(e){ if(e.key==='Enter') attempt(); });
    setTimeout(function(){ var i=document.getElementById('_pwIn'); if(i) i.focus(); },150);
  }
  if(document.body) mount(); else document.addEventListener('DOMContentLoaded',mount);
})();
