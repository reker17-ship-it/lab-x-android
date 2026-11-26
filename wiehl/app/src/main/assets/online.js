'use strict';
// Preserve the original single-device game independently of any live duel.
let net = null;
const nativeRender = render, nativeSave = save;
const nativeActions = {roll, buy, upgrade, endTurn};
const allowedPhase = {roll:['ready'],buy:['buy'],upgrade:['upgrade'],endTurn:['buy','upgrade','end']};
const introText = 'Spielt auf zwei Handys. Beide brauchen Internet und dieselbe Online-App.';
const onlineDialog = $('online-dialog');
const codeAlphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
function newCode() {
  const values = crypto.getRandomValues(new Uint8Array(10));
  return Array.from(values, v=>codeAlphabet[v%codeAlphabet.length]).join('');
}
function nameOf(id, fallback) {return $(id).value.trim().slice(0,22)||fallback;}
function onlineUi(message) {
  if(message!==undefined){
    if(net) net.message=message;
    else $('online-message').textContent=message;
  }
  $('online-setup').hidden=!!net;
  $('online-room').hidden=!net;
  $('online-button').textContent=net?'Online-Duell':'Online spielen';
  $('online-room-code').value=net?net.code:'';
  $('online-copy').disabled=!net||!net.code;
  $('online-leave').disabled=busy;
  if(net){
    $('online-message').textContent=net.message||'Verbindung wird aufgebaut …';
    $('online-status').textContent=(net.role==='host'?'Gastgeber · ':'Gast · ')+(net.ready?'Verbunden':net.message||'Verbindung wird aufgebaut');
  } else $('online-status').textContent='Lokal · zwei Personen auf einem Gerät';
}
function showOnline(){
  if(!net){
    $('online-host-name').value=state.players[0].name;
    $('online-guest-name').value=state.players[1].name;
    $('online-message').textContent=introText;
  }
  onlineUi();
  if(!onlineDialog.open) onlineDialog.showModal();
}
function canPlay(){
  if(!net)return true;
  return net.ready&&!net.pending&&state.active===(net.role==='host'?0:1);
}
save=function(){
  if(!net)nativeSave();
};
render=function(){
  nativeRender();
  if(net){
    $('new-button').disabled=true;
    const label=document.querySelector('.game-meta span');
    if(label)label.textContent='2 Personen · online';
    if(!canPlay()||state.phase==='finished'){
      $('actions').querySelectorAll('button').forEach(button=>button.disabled=true);
      if(!net.ready) $('turn').textContent='Warte auf Verbindung';
      else if(net.pending)$('turn').textContent='Zug wird übertragen …';
      else if(state.phase!=='finished'&&!canPlay())$('turn').textContent=player().name+' ist am Zug · bitte warten';
    }
    onlineUi();
  }else{
    const label=document.querySelector('.game-meta span');
    if(label)label.textContent='2 Personen · ein Gerät';
    onlineUi();
  }
};
function send(session,packet){
  if(net!==session||!session.conn||!session.conn.open)return false;
  try {session.conn.send(packet);return true;}
  catch(_){onlineUi('Übertragung fehlgeschlagen. Prüft die Internetverbindung.');return false;}
}
function broadcast(session){
  if(session?.role==='host'&&session.ready)send(session,{type:'state',version:1,state:state});
}
const localSettle=settle;
settle=function(){
  localSettle();
  if(net?.role==='host')broadcast(net);
};
function validMove(move){
  return typeof move==='string'&&Object.prototype.hasOwnProperty.call(allowedPhase,move)&&allowedPhase[move].includes(state.phase)&&!busy;
}
function requestMove(move){
  if(!validMove(move)||!canPlay())return;
  if(!net||net.role==='host')return nativeActions[move]();
  const session=net;
  session.pending=true;render();
  if(!send(session,{type:'move',version:1,move})){
    session.pending=false;render();
    return;
  }
  clearTimeout(session.moveTimer);
  session.moveTimer=setTimeout(()=>{
    if(net!==session||!session.pending)return;
    session.pending=false;
    onlineUi('Keine Antwort. Prüft eure Verbindung.');
    if(session.conn)send(session,{type:'sync',version:1});
    render();
  },12000);
}
roll=()=>requestMove('roll');
buy=()=>requestMove('buy');
upgrade=()=>requestMove('upgrade');
endTurn=()=>requestMove('endTurn');
function validState(s){
  return !!s&&Array.isArray(s.players)&&s.players.length===2&&s.players.every(p=>p&&typeof p.name==='string'&&p.name.length<=22&&Number.isFinite(p.money)&&Number.isInteger(p.pos)&&p.pos>=0&&p.pos<board.length)&&
    Array.isArray(s.deeds)&&s.deeds.length===board.length&&s.deeds.every(d=>d===null||((d.owner===0||d.owner===1)&&typeof d.upgraded==='boolean'))&&
    [0,1].includes(s.active)&&Number.isInteger(s.round)&&s.round>=1&&s.round<=rounds&&['ready','buy','upgrade','end','finished'].includes(s.phase)&&
    Array.isArray(s.deck)&&s.deck.every(x=>Number.isInteger(x)&&x>=0&&x<cards.length)&&Array.isArray(s.dice)&&s.dice.every(x=>Number.isInteger(x)&&x>=1&&x<=6)&&
    typeof s.headline==='string'&&typeof s.message==='string'&&Array.isArray(s.log)&&s.log.every(x=>typeof x==='string');
}
function receive(session,packet){
  if(net!==session||!packet||packet.version!==1)return;
  if(session.role==='host'){
    if(packet.type==='hello'&&!session.ready){
      if(!session.started){
        state.players[1].name=typeof packet.name==='string'?packet.name.trim().slice(0,22)||'Spieler 2':'Spieler 2';
        session.started=true;
      }
      session.ready=true;
      onlineUi('Mit '+state.players[1].name+' verbunden');
      render();broadcast(session);
      if(onlineDialog.open)onlineDialog.close();
    }else if(session.ready&&packet.type==='sync'){
      broadcast(session);
    }else if(session.ready&&packet.type==='move'){
      if(state.active===1&&validMove(packet.move))nativeActions[packet.move]();
      else if(!busy)broadcast(session);
    }
  }else if(packet.type==='state'&&validState(packet.state)){
    state=packet.state;selected=state.players[state.active].pos;
    session.ready=true;session.pending=false;clearTimeout(session.moveTimer);
    onlineUi('Mit '+state.players[0].name+' verbunden');
    render();
    if(onlineDialog.open)onlineDialog.close();
  }
}
function attach(session,conn){
  if(net!==session)return conn.close();
  if(session.conn&&session.conn!==conn)return conn.close();
  session.conn=conn;session.ready=false;
  clearTimeout(session.connectTimer);
  session.connectTimer=setTimeout(()=>{
    if(net===session&&session.conn===conn&&!session.ready){
      onlineUi('Keine Verbindung. Prüft Spielcode und Internet.');conn.close();
      if(session.conn===conn){session.conn=null;session.ready=false;}
      render();showOnline();
    }
  },30000);
  conn.on('open',()=>{
    if(net!==session||session.conn!==conn)return;
    onlineUi('Spielstand wird abgeglichen …');
    if(session.role==='guest')send(session,{type:'hello',version:1,name:session.name});
    render();
  });
  conn.on('data',packet=>{
    if(net!==session||session.conn!==conn)return;
    receive(session,packet);
    if(session.ready)clearTimeout(session.connectTimer);
  });
  function lost(){
    if(net!==session||session.conn!==conn)return;
    session.conn=null;session.ready=false;session.pending=false;
    clearTimeout(session.connectTimer);clearTimeout(session.moveTimer);
    onlineUi(session.role==='host'?'Verbindung getrennt. Der Mitspieler kann mit demselben Code wieder beitreten.':'Verbindung getrennt. Verlasse das Online-Spiel und tritt mit demselben Code erneut bei.');
    render();
  }
  conn.on('close',lost);
  conn.on('error',()=>{lost();try{conn.close();}catch(_){}});
}
function exitOnline(message){
  if(!net||busy)return;
  const old=net;net=null;
  clearTimeout(old.connectTimer);clearTimeout(old.moveTimer);
  try{old.peer?.destroy();}catch(_){}
  state=old.previous;selected=old.previousSelected;
  busy=false;render();
  $('online-message').textContent=message||introText;
}
function startOnline(role){
  if(net||busy)return;
  const PeerClass=window.Peer||window.peerjs?.Peer;
  if(typeof PeerClass!=='function'){
    onlineUi('Online-Verbindung ist nicht verfügbar. Lokales Spielen funktioniert weiterhin.');return;
  }
  const code=role==='host'?newCode():$('online-join-code').value.trim().toUpperCase();
  if(!/^[A-HJ-NP-Z2-9]{10}$/.test(code)){
    onlineUi('Bitte den zehnstelligen Spielcode eingeben.');return;
  }
  const session={role,code,name:nameOf(role==='host'?'online-host-name':'online-guest-name',role==='host'?'Spieler 1':'Spieler 2'),
    previous:state,previousSelected:selected,ready:false,pending:false,started:false,peer:null,conn:null};
  net=session;
  state=fresh(role==='host'?[session.name,'Spieler 2']:['Spieler 1',session.name]);selected=0;
  onlineUi('Verbindung zum Spieldienst wird aufgebaut …');render();
  const hostId='wiehl-v1-'+code;
  try{
    session.peer=role==='host'?new PeerClass(hostId,{secure:true}):new PeerClass({secure:true});
  }catch(_){exitOnline('Verbindung konnte nicht gestartet werden.');return;}
  const peer=session.peer;
  session.connectTimer=setTimeout(()=>{
    if(net===session&&!session.ready&&(!peer.open||role==='guest'))exitOnline('Spieldienst nicht erreichbar. Bitte erneut versuchen.');
  },30000);
  peer.on('open',()=>{
    if(net!==session)return;
    clearTimeout(session.connectTimer);
    if(role==='host'){
      onlineUi('Teile den Spielcode und warte auf deinen Mitspieler.');
      render();
    }else{
      onlineUi('Verbinde mit dem Gastgeber …');
      attach(session,peer.connect(hostId,{reliable:true,serialization:'json'}));
      render();
    }
  });
  peer.on('connection',conn=>{
    if(net!==session||role!=='host'||session.conn){conn.close();return;}
    attach(session,conn);
  });
  peer.on('disconnected',()=>{
    if(net!==session||peer.destroyed)return;
    if(!session.ready)onlineUi('Spieldienst getrennt. Verbindung wird erneut versucht.');
    try{peer.reconnect();}catch(_){}
  });
  peer.on('error',err=>{
    if(net!==session)return;
    if(session.ready)return;
    const message=err?.type==='peer-unavailable'?'Spielcode nicht gefunden. Ist der Gastgeber noch in der App?':err?.type==='unavailable-id'?'Dieser Code ist bereits belegt. Erstelle einen neuen.':'Online-Verbindung fehlgeschlagen. Bitte Internet prüfen und erneut versuchen.';
    if(!busy)exitOnline(message);
    else onlineUi(message);
  });
}
$('online-button').addEventListener('click',showOnline);
$('online-create').addEventListener('click',()=>startOnline('host'));
$('online-join').addEventListener('click',()=>startOnline('guest'));
$('online-close').addEventListener('click',()=>onlineDialog.close());
$('online-leave').addEventListener('click',()=>{
  if(!busy)exitOnline('Online-Spiel beendet. Dein lokales Spiel wurde wiederhergestellt.');
});
$('online-copy').addEventListener('click',async()=>{
  if(!net)return;
  const code=net.code;
  try{await navigator.clipboard.writeText(code);onlineUi('Spielcode kopiert. Du kannst ihn jetzt verschicken.');}
  catch(_){const input=$('online-room-code');input.focus();input.select();input.setSelectionRange(0,code.length);
    try{if(document.execCommand('copy'))onlineUi('Spielcode kopiert. Du kannst ihn jetzt verschicken.');else onlineUi('Der Code ist markiert. Halte ihn gedrückt und wähle Kopieren.');}
    catch(_){onlineUi('Der Code ist markiert. Halte ihn gedrückt und wähle Kopieren.');}
  }
});
render();
