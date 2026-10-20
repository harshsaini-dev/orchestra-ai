// Motion is a view of persisted events. It does not invent agent activity.
export const AGENTS=['Enquiry','Data','Policy','Task','Report','Notification','Auditor','Orchestrator'];
const POINTS=[[125,125],[265,65],[440,65],[580,125],[575,265],[435,325],[220,315],[345,190]];
const COLORS=['#b5b0d0','#9dbbcc','#d5c398','#e6a582','#b0c8a9','#b4bdc5','#92bdb3','#e6a582'];
export class SpatialGraph{
 constructor(host,onSelect){
  this.host=host;this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  host.innerHTML=`<div class="graph-caption"><span>AGENT NETWORK / 08 NODES</span><span id="graph-mode">AWAITING WORKFLOW</span></div><svg viewBox="0 0 700 410" role="group" aria-label="Agent execution network"><defs><pattern id="floor" width="44" height="24" patternUnits="userSpaceOnUse"><path class="floor" d="M0 12L22 0L44 12L22 24Z"/></pattern></defs><path d="M20 180L350 0L680 180L350 400Z" fill="url(#floor)"/>${POINTS.slice(0,7).map(([x,y],i)=>`<path class="edge" id="route-${i}" d="M345 190Q${x} 190 ${x} ${y}"/>`).join('')}<g class="packets"></g>${AGENTS.map((name,i)=>`<g class="node idle" style="--node:${COLORS[i]}" data-agent="${name}" transform="translate(${POINTS[i][0]} ${POINTS[i][1]})" role="button" tabindex="0" aria-label="Inspect ${name}"><title>${name}: idle</title><ellipse class="shadow" cy="28" rx="42" ry="15"/><g class="object"><path class="left" d="M-38 0L0 22L0 35L-38 13Z"/><path class="right" d="M0 22L38 0L38 13L0 35Z"/><path class="top" d="M0-22L38 0L0 22L-38 0Z"/><path class="inset" d="M0-12L21 0L0 12L-21 0Z"/><text class="symbol" y="4">${i===7?'O':String(i+1).padStart(2,'0')}</text></g><text class="label" y="56">${name.toUpperCase()}</text><text class="state" y="71">IDLE</text></g>`).join('')}</svg><div class="graph-note"><span>Click an agent to inspect its evidence</span><span>Persisted messages · SSE</span></div>`;
  const activate=e=>{const n=e.target.closest('[data-agent]');if(n)onSelect(n.dataset.agent)};
  host.addEventListener('click',activate);host.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)&&e.target.closest('[data-agent]')){e.preventDefault();activate(e)}});
  const svg=host.querySelector('svg');host.addEventListener('pointermove',e=>{if(this.reduced||e.pointerType==='touch')return;const r=host.getBoundingClientRect();svg.style.transform=`rotateX(${-(e.clientY-r.top-r.height/2)/r.height*5}deg) rotateY(${(e.clientX-r.left-r.width/2)/r.width*7}deg)`});host.addEventListener('pointerleave',()=>svg.style.transform='');
 }
 update(events,selected,replay=false){
  this.replay=replay;this.host.querySelector('#graph-mode').textContent=replay?'HISTORICAL REPLAY':events.length?'RECORDED EXECUTION':'AWAITING WORKFLOW';
  const states={};events.forEach(e=>{if(e.type==='agent_state_changed')states[e.agent]=e.detail.state});
  if(events.length)states.Orchestrator=events.some(e=>e.type==='run_done')?'done':events.some(e=>e.type==='run_error')?'error':'working';
  this.host.querySelectorAll('[data-agent]').forEach(n=>{const name=n.dataset.agent,state=states[name]||'idle';n.setAttribute('class',`node ${state} ${selected===name?'selected':''}`);n.querySelector('.state').textContent=state.toUpperCase().replace('_',' ');n.querySelector('title').textContent=name+': '+state;n.setAttribute('aria-pressed',String(name===selected))});
 }
 packet(message){
  if(this.reduced)return;
  const from=AGENTS.indexOf(message.from),to=AGENTS.indexOf(message.to),index=from===7?to:from;if(index<0||index>=7)return;
  const path=this.host.querySelector('#route-'+index),layer=this.host.querySelector('.packets');if(!path?.getTotalLength)return;
  if(layer.children.length>=16)layer.firstChild.remove();
  const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');dot.setAttribute('r','3');dot.setAttribute('fill',COLORS[index]);layer.append(dot);
  const length=path.getTotalLength(),start=performance.now();
  const step=now=>{if(!dot.isConnected)return;const progress=Math.min(1,(now-start)/900),p=path.getPointAtLength((from===7?progress:1-progress)*length);dot.setAttribute('cx',p.x);dot.setAttribute('cy',p.y);if(progress<1)requestAnimationFrame(step);else dot.remove()};requestAnimationFrame(step);
 }
}
