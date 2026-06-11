/**
 * cv_simple.js — CourtVision CV page renderer. No external deps.
 * Contract IDs: #cv-header #wp-bar #intel-narrative #pop-off
 *   #scenarios #box-home #box-away #bets-list #book-picker
 */
"use strict";
let _board=null,_isLive=false;
let _pollT=null,_intelT=null,_slateT=null,_paused=false;
const _BOOK_KEY="cv_book_picker";
const GRADE_CLR={A:"#22c55e",B:"#60a5fa",C:"#94a3b8"};
// Canonical book names as they appear in _books_full from the backend.
// "all" is the default cross-book best mode. FanDuel removed 2026-06-10: its
// live feed is threshold-only (one-sided, no Under) so it cannot produce a real
// two-sided per-book quote — only DK + Pinnacle expose genuine O/U prices.
const BOOKS=["all","DraftKings","Pinnacle"];
const BOOK_LBL={"all":"Best Price","DraftKings":"DraftKings","Pinnacle":"Pinnacle"};
// Map picker key → partial lowercase match against _books_full[].book
const BOOK_MATCH={"DraftKings":"draftkings","Pinnacle":"pinnacle"};

document.addEventListener("DOMContentLoaded",()=>{
  const el=document.getElementById("cv-board");
  if(el){try{_board=JSON.parse(el.textContent);}catch(_){}}
  if(_board&&Object.keys(_board).length)_all(_board);
  _renderBookPicker(); _schedPoll();
  _fetchIntel(); _fetchSlate();
  document.addEventListener("visibilitychange",()=>{
    _paused=document.hidden;
    if(!_paused){_fetchIntel();_fetchSlate();_doPoll();}
  });
});

// ── Live poll ────────────────────────────────────────────────────────────────
// Poll /api/cv_live for the live overlay (score, win-prob, box go-live, final
// gate). 10s live / 15s pregame. One bad tick never blanks the page — on error
// the last-good _board stays rendered and the next tick retries.
function _schedPoll(){clearTimeout(_pollT);_pollT=setTimeout(_doPoll,_isLive?10000:15000);}
async function _doPoll(){
  if(_paused){_schedPoll();return;}
  try{const r=await fetch(`/api/cv_live?date=${_gdate()}&game_id=${_gid()}`);if(r.ok){const b=await r.json();if(b&&b.game){_board=b;_all(b);}}}catch(_){}
  _schedPoll();
}
async function _fetchIntel(){
  clearTimeout(_intelT);
  try{const r=await fetch(`/api/cv_intel?date=${_gdate()}&game_id=${_gid()}`);if(r.ok){const d=await r.json();_renderIntel(d);}}catch(_){}
  _intelT=setTimeout(_fetchIntel,_isLive?15000:30000);
}
async function _fetchSlate(){
  clearTimeout(_slateT);
  try{const r=await fetch(`/api/slate?date=${_gdate()}&game_id=${_gid()}`);if(r.ok){const d=await r.json();_renderBets(d?.bets||[]);}}catch(_){}
  // Dropped from 60s → 25s pregame so cards re-rank as lines move
  _slateT=setTimeout(_fetchSlate,_isLive?15000:25000);
}

// ── Master render ────────────────────────────────────────────────────────────
function _all(b){
  _isLive=b?.live?.is_live??false;
  _hdr(b);_wpbar(b);_box(b);_scen(b);_hon(b);_meta(b);
}

// ── Header ───────────────────────────────────────────────────────────────────
function _hdr(b){
  const el=_qs("#cv-header");if(!el||!b.game)return;
  const g=b.game,wp=b.win_prob,sc=b.score,lv=b.live||{};
  const hA=g.home?.abbr||"NYK",aA=g.away?.abbr||"SAS";
  const hC=g.home?.color||"#f97316",aC=g.away?.color||"#60a5fa";
  const isLive=lv?.is_live===true,isFinal=lv?.is_final===true;
  // Win% headline tracks the live (terminal-gated) number during/after a game.
  const liveH=isLive&&lv?.win_prob_home_live!=null?lv.win_prob_home_live:null;
  const h=liveH!=null?liveH:(wp?.headline_home??0.492);
  const chips=(wp?.engine_split||[]).map(e=>{
    const cls=e.primary?" is-primary":e.secondary?" is-secondary":"";
    return`<span class="engine-chip${cls}"><span class="ec-lbl">${_e(e.label)}</span><span class="ec-val">${_f(e.home??0,100)}%</span></span>`;
  }).join("");
  const tot=sc?.total_trust_low&&sc?.total_trust_high?`${sc.total_trust_low}–${sc.total_trust_high}`:(sc?.total_raw??212);
  const badge=isFinal?'<span class="live-badge final">FINAL</span>':isLive?'<span class="live-badge">LIVE</span>':"";
  // Win caption + framing reflect game state.
  const winCap=isFinal?`${hA} — final`:isLive?`${hA} live win probability`:`${hA} win probability`;
  let framing;
  if(isLive||isFinal){
    const per=isFinal?"FINAL":(lv.period!=null?`Q${lv.period}${lv.clock?" "+lv.clock:""}`:"live");
    framing=`${aA} ${lv.away_score??"—"} – ${hA} ${lv.home_score??"—"} · ${per}`;
  } else { framing=wp?.framing||"coin flip"; }
  // Score block: live score when in-game, projected final pregame.
  const scBlock=(isLive||isFinal)
    ? `<div class="hdr-cap">${isFinal?"final score":"current score"}</div>
       <div class="hdr-sc"><span class="ps-team" style="color:${hC}">${hA} ${lv.home_score??"—"}</span><span class="ps-dash">–</span><span class="ps-team" style="color:${aC}">${aA} ${lv.away_score??"—"}</span></div>
       <div class="hdr-tot">proj final ~${sc?.home??106}–${sc?.away??108}${isFinal?"":` · ${aA} leads bar = live`}</div>`
    : `<div class="hdr-cap">projected final</div>
       <div class="hdr-sc"><span class="ps-team" style="color:${hC}">${hA} ${sc?.home??106}</span><span class="ps-dash">–</span><span class="ps-team" style="color:${aC}">${aA} ${sc?.away??108}</span></div>
       <div class="hdr-tot">Total <b>~${tot}</b>${sc?.total_biased?'<span class="biased-pill">deflated</span>':""}</div>`;
  el.innerHTML=`<div class="hdr-s">${_e(g.series||"")} · G4 · ${g.date||_gdate()}${badge}</div>
<div class="hdr-m"><span style="color:${aC}">${aA}</span><span class="hdr-at">@</span><span style="color:${hC}">${hA}</span></div>
<div class="hdr-hero">
  <div class="hdr-win">
    <div class="hdr-cap">${_e(winCap)}</div>
    <div class="hdr-big" style="color:${hC}">${_f(h,100)}%</div>
    <div class="hdr-fr">${_e(framing)}</div>
  </div>
  <div class="hdr-proj">${scBlock}</div>
</div>
<div class="hdr-eng">${chips}</div>
${wp?.reconciliation&&!isLive&&!isFinal?`<div class="hdr-recon">${_e(wp.reconciliation)}</div>`:""}`;
}

// ── Win-prob bar ──────────────────────────────────────────────────────────────
function _wpbar(b){
  const el=_qs("#wp-bar");if(!el)return;
  const wp=b.win_prob,lv=b.live,g=b.game;
  const h=_isLive?(lv?.win_prob_home_live??wp?.headline_home??0.492):(wp?.headline_home??0.492),a=1-h;
  const hC=g?.home?.color||"#f97316",aC=g?.away?.color||"#60a5fa";
  const isFinal=lv?.is_final===true;
  const stale=isFinal?"FINAL":_isLive&&lv?.snapshot_age_sec!=null?`live · ${Math.round(lv.snapshot_age_sec)}s ago`:_isLive?"live":"pregame projection";
  el.innerHTML=`<div class="wp-wrap"><div id="wp-bar-away" style="width:${_f(a,100)}%;background:${aC}"></div><div id="wp-bar-home" style="width:${_f(h,100)}%;background:${hC}"></div></div>
<div class="wp-labels"><span style="color:${aC}">${g?.away?.abbr||"SAS"} ${_f(a,100)}%</span><span style="color:${hC}">${g?.home?.abbr||"NYK"} ${_f(h,100)}%</span></div>
<div class="wp-stale">${stale}</div>`;
}

// ── Box score ─────────────────────────────────────────────────────────────────
function _box(b){
  const g=b.game,bs=b.box_score;if(!bs)return;
  const C=["pts","reb","ast","fg3m","stl","blk","tov"],L=["PTS","REB","AST","3PM","STL","BLK","TOV"];
  const playoffAdj=b?.meta?.playoff_adjusted===true;
  function _playerRow(p,isDnp){
    const lv=p.live;
    const minLabel=p.minutes!=null?`<span class="bs-min">${Math.round(p.minutes)}m</span>`:"";
    const nm=`<td class="bs-n"><span class="bs-nm">${p.starter?'<span class="sd"></span>':""}${_e(p.name||"")}${minLabel}</span>${p.lean?`<span class="lt">${_e(p.lean)}</span>`:""}${p.foul_count!=null?`<span class="fp">${p.foul_count}F</span>`:""}</td>`;
    if(isDnp){
      const empties=C.map(()=>`<td class="bc"><span class="cmid dnp-stat">—</span></td>`).join("");
      return`<tr class="bs-dnp-row">${nm}${empties}</tr>`;
    }
    const cells=C.map(c=>{
      const s=p.stats?.[c];
      if(_isLive&&lv){const ac=lv[c]??"—",pf=lv[`proj_${c}`]??lv?.proj_final?.[c]??null;return`<td class="bc lv" title="Pre:${s?.q50??"—"}|Act:${ac}${pf!=null?"|Fin:"+pf:""}"><span class="cmid pr">${s?.q50??"—"}</span><span class="crng"><span class="ac">${ac}</span>${pf!=null?` <span class="pf">→${pf}</span>`:""}</span></td>`;}
      if(!s)return`<td class="bc"><span class="cmid">—</span></td>`;
      const r=s.q10!=null&&s.q90!=null?`${s.q10}–${s.q90}`:"";
      return`<td class="bc" title="${r?"q10–q90: "+r:""}"><span class="cmid">${_f1(s.q50??0)}</span>${r?`<span class="crng">${r}</span>`:""}</td>`;
    }).join("");
    return`<tr>${nm}${cells}</tr>`;
  }
  function team(side,ti,players){
    if(!players?.length)return'<p class="pending">No roster data.</p>';
    const hasDnpData=players.some(p=>p.dnp!=null);
    let activePlayers=players,dnpPlayers=[];
    if(hasDnpData){activePlayers=players.filter(p=>!p.dnp);dnpPlayers=players.filter(p=>p.dnp);}
    const activeRows=activePlayers.map(p=>_playerRow(p,false)).join("");
    let dnpSection="";
    if(dnpPlayers.length){
      const dnpRows=dnpPlayers.map(p=>_playerRow(p,true)).join("");
      dnpSection=`<tbody class="bs-dnp-body"><tr><td colspan="${C.length+1}" class="dnp-header">Did not play (projected)</td></tr>${dnpRows}</tbody>`;
    }
    const note=_isLive?'pre · live → final':"q50 · q10–q90 below";
    const paTag=playoffAdj?'<span class="playoff-adj-tag">playoff-adjusted rotation</span>':"";
    return`<div class="bs-lbl"><span class="bs-abbr" style="color:${ti?.color||"#e2e8f0"}">${_e(ti?.abbr||side)}</span><span class="bs-full">${_e(ti?.name||"")}</span>${paTag}<span class="bs-note">${note}</span></div><div class="bs-sc"><table class="bs-t"><thead><tr><th>Player</th>${L.map(l=>`<th>${l}</th>`).join("")}</tr></thead><tbody>${activeRows}</tbody>${dnpSection}</table></div>`;
  }
  const hEl=_qs("#box-home"),aEl=_qs("#box-away");
  if(hEl)hEl.innerHTML=team("home",g?.home,bs.home);
  if(aEl)aEl.innerHTML=team("away",g?.away,bs.away);
  if(!hEl&&!aEl){const l=_qs("#box-score");if(l)l.innerHTML=team("home",g?.home,bs.home)+team("away",g?.away,bs.away);}
}

// ── Intel (#intel-narrative, #pop-off, from /api/cv_intel) ───────────────────
function _renderIntel(d){
  const n=_qs("#intel-narrative");
  if(n){
    const wn=d?.whats_next?`<p class="intel-next">${_e(d.whats_next)}</p>`:"";
    n.innerHTML=d?.narrative?`<p>${_e(d.narrative)}</p>${wn}`:'<span class="pending">Reading the model…</span>';
  }
  // Sub-line: live/final state · narrative engine · update time.
  const sub=_qs("#intel-updated");
  if(sub){
    const tag=d?.is_final?'<span class="live-badge final">FINAL</span> ':d?.is_live?'<span class="live-badge">LIVE</span> ':"";
    const src=d?.source?_e(d.source):"";
    const t=d?.updated_at?new Date(d.updated_at).toLocaleTimeString():"";
    sub.innerHTML=`${tag}${src}${t?` · ${t}`:"updates on a cadence"}`;
  }
  // Pop-off: the server already merges live standouts + board reads + longshots
  // (deduped). Render it directly — no client-side longshot re-merge (dup fix).
  const chips=(d?.pop_off||[]).slice(0,10);
  const po=_qs("#pop-off");
  if(po)po.innerHTML=chips.length?chips.map(p=>{
    const t=(p.tier||"").toUpperCase();
    const tag=t?`<span class="pop-tier tier-${_e(t)}">${_e(t==="LONGSHOT"?"longshot":t.toLowerCase())}</span>`:"";
    return`<div class="pop-c"><div class="pop-top"><span class="pop-n">${_e(p.player||"")}</span>${tag}</div>${p.why?`<div class="pop-w">${_e(p.why||"")}</div>`:""}</div>`;
  }).join(""):'<span class="pending">—</span>';
}

// ── Scenarios ─────────────────────────────────────────────────────────────────
function _scen(b){
  const el=_qs("#scenarios");if(!el)return;
  const sc=b?.market_board?.scenarios;if(!sc?.length)return;
  const mx=Math.max(...sc.map(s=>s.p||0),0.01);
  el.innerHTML=sc.map(s=>{
    const w=Math.round(((s.p||0)/mx)*100);
    return`<div class="sc-r"><span class="sc-lbl">${_e(s.label||"")}</span><span class="sc-bar"><i style="width:${w}%"></i></span><span class="sc-p">${_pct(s.p)}</span></div>`;
  }).join("");
}

// ── Book picker + bets ────────────────────────────────────────────────────────
function _selBook(){return localStorage.getItem(_BOOK_KEY)||"all";}

function _renderBookPicker(){
  const el=_qs("#book-picker");if(!el)return;
  const cur=_selBook();
  el.innerHTML=BOOKS.map(b=>`<button class="bk-btn${b===cur?" active":""}" onclick="window._pb('${b}')">${_e(BOOK_LBL[b]||b)}</button>`).join("");
}

window._pb=function(b){localStorage.setItem(_BOOK_KEY,b);_renderBookPicker();_fetchSlate();};

/**
 * Build a book_quotes map from a bet's _books_full array.
 * Returns { "DraftKings": {line, over, under}, "FanDuel": {...}, ... }
 * Uses the bet's own line since _books_full doesn't store it separately.
 */
function _buildBookQuotes(bet){
  const full=(bet._books_full||[]);
  const line=bet.line;
  const out={};
  for(const bf of full){
    const bname=bf.book||"";
    if(!bname)continue;
    out[bname]={
      line:line,
      over:bf.over_odds??null,
      under:bf.under_odds??null,
    };
  }
  return out;
}

/**
 * Get the quote for the selected book on a bet.
 * Returns {bookLabel, line, price, found} where found=false means no quote.
 * "all" mode: use best_book + best_price (cross-book best).
 */
function _bookQuote(bet, bookKey){
  if(!bookKey||bookKey==="all"){
    // Default best-price mode: use whatever the backend picked
    const bk=bet.best_book||"";
    const px=bet.best_price??null;
    return{bookLabel:bk||"Best",line:bet.line,price:px,found:px!=null};
  }
  const matchStr=BOOK_MATCH[bookKey]||bookKey.toLowerCase();
  const quotes=_buildBookQuotes(bet);
  // Find the matching book entry (case-insensitive partial match)
  const key=Object.keys(quotes).find(k=>k.toLowerCase().includes(matchStr)||matchStr.includes(k.toLowerCase()));
  if(!key)return{bookLabel:bookKey,line:bet.line,price:null,found:false};
  const q=quotes[key];
  const sideKey=bet.side==="OVER"?"over":"under";
  const price=q[sideKey]??null;
  return{bookLabel:key,line:q.line,price,found:price!=null};
}

function _renderBets(bets){
  const el=_qs("#bets-list");if(!el)return;
  if(!bets?.length){el.innerHTML='<p class="pending">No bets — drop a lines CSV to grade EV.</p>';return;}
  const bk=_selBook();

  // Re-rank: bets the selected book offers (has a real quote) come first,
  // then by grade, then by EV descending.
  const go={A:0,B:1,C:2};
  const r=[...bets].sort((a,b)=>{
    const aq=_bookQuote(a,bk),bq=_bookQuote(b,bk);
    const ah=aq.found?0:1,bh=bq.found?0:1;
    if(ah!==bh)return ah-bh;
    const ag=go[a.grade?.[0]]??9,bg=go[b.grade?.[0]]??9;
    return ag!==bg?ag-bg:(b.ev_pct||0)-(a.ev_pct||0);
  });

  el.innerHTML=r.map(bet=>{
    const g=(bet.grade||"C")[0].toUpperCase(),gc=GRADE_CLR[g]||"#94a3b8";
    const q=_bookQuote(bet,bk);
    const side=bet.side?_e(bet.side):"";
    // Use the quote line when available (some books have alt lines), fallback to bet.line
    const dispLine=q.line??bet.line;
    const prop=`${_e(bet.prop_stat||"").toUpperCase()}${dispLine!=null?` ${side?side+" ":""}${dispLine}`:(side?` ${side}`:"")}`;

    // All-books comparison chips (for the bottom row)
    const fullChips=(_buildBookQuotes_flat(bet,bet.side)).slice(0,4).map(e=>{
      const isSel=bk!=="all"&&(e.book||"").toLowerCase().includes((BOOK_MATCH[bk]||bk.toLowerCase()));
      return`<span class="bkc${isSel?" sel":""}" onclick="window._pb('${_e(e.book||"")}')">${_e(e.book||"")} ${_odds(e.price)}</span>`;
    }).join("");

    // "predictions vs odds": the model's per-player probability next to the
    // market-implied probability, plus the conservatively-graded EV. The model%
    // traces to the player's own distribution; EV uses the calibrated prob.
    const meta=[];
    if(bet.model_prob!=null)meta.push(`model ${_f1(bet.model_prob*100)}%`);
    if(bet.market_prob!=null)meta.push(`mkt ${_f1(bet.market_prob*100)}%`);
    if(bet.ev_pct!=null)meta.push(`EV ${bet.ev_pct>0?"+":""}${bet.ev_pct.toFixed(1)}%`);

    // Book label + price display
    let bookLbl,pxDisp;
    if(q.found){
      bookLbl=_e(q.bookLabel);
      pxDisp=_odds(q.price);
    } else {
      bookLbl=`<span class="no-book-line">${_e(bk==="all"?"—":`no ${_e(BOOK_LBL[bk]||bk)} line`)}</span>`;
      // Fallback to best available price
      pxDisp=bet.best_price!=null?_odds(bet.best_price):"—";
    }

    return`<div class="bet-c" data-grade="${g}">
<div class="bet-g" style="background:${gc}">${g}</div>
<div class="bet-main"><div class="bet-p">${_e(bet.player_name||"")}</div><div class="bet-s">${prop}</div>${bet.grade_note?`<div class="bet-n">${_e(bet.grade_note)}</div>`:""}</div>
<div class="bet-odds"><div class="bet-book">${bookLbl}</div><div class="bet-px">${pxDisp}</div>${meta.length?`<div class="bet-ev">${meta.join(" · ")}</div>`:""}</div>
${fullChips?`<div class="bet-bks">${fullChips}</div>`:""}
<div class="bet-d">projection · playoffs: no proven edge · paper only</div></div>`;
  }).join("");
}

/**
 * Flatten _books_full to [{book, price}] for the given side — used for chips.
 */
function _buildBookQuotes_flat(bet, side){
  const sideKey=(side||"OVER")==="OVER"?"over_odds":"under_odds";
  const full=(bet._books_full||[]);
  const out=[];
  for(const bf of full){
    const px=bf[sideKey]??null;
    if(px!=null)out.push({book:bf.book||"",price:px});
  }
  out.sort((a,b)=>b.price-a.price);
  return out;
}

// ── Honesty + meta ────────────────────────────────────────────────────────────
function _hon(b){const el=_qs("#honesty-footer");if(!el||!b.honesty)return;const h=b.honesty;el.innerHTML=`<p class="disc-main">${_e(h.disclaimer||"")}</p>${h.total_biased_note?`<p class="disc-note"><strong>Total:</strong> ${_e(h.total_biased_note)}</p>`:""}${h.ast_note?`<p class="disc-note"><strong>AST:</strong> ${_e(h.ast_note)}</p>`:""}<p class="disc-meta" id="meta-line"></p>`;}
function _meta(b){const el=_qs("#meta-line");if(!el||!b.meta)return;el.textContent=`Built ${b.meta.built_at?new Date(b.meta.built_at).toLocaleTimeString():"—"} · ${b.meta.source||""}${b.meta.stale?" · STALE":""}`;}

// ── Utils ─────────────────────────────────────────────────────────────────────
const _qs=sel=>document.querySelector(sel);
const _gid=()=>_board?.game?.game_id||"0042500404";
const _gdate=()=>_board?.game?.date||"2026-06-10";
const _f=(n,m=1)=>typeof n==="number"?(n*m).toFixed(1):String(n??"");
const _f1=n=>typeof n==="number"?n.toFixed(1):String(n??"");
const _pct=n=>typeof n==="number"?(n*100).toFixed(0)+"%":"—";
const _odds=n=>{if(n==null)return"—";const v=Number(n);return isNaN(v)?String(n):v>0?`+${v}`:String(v);};
const _e=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");

// Wired: book-picker persists localStorage + re-ranks/re-prices bets on change.
// "Best Price" (all) = cross-book best from backend. DK/Pin = per-book quote
//   from _books_full (both sides). FanDuel is dropped (threshold-only feed). If a
//   book has no quote for a prop, shows a "no <book> line" badge + best price.
// Live: poll /api/cv_live (10s live / 15s pregame); board+box+win-prob go live,
//   win-prob terminal-gates to 0/100 at the buzzer, FINAL is labelled.
// Intel: /api/cv_intel 15s live / 30s pregame. Slate: 15s live / 25s pregame.
// Tab-hidden pause via visibilitychange. One bad fetch never blanks the page.
