// O1/O2: isometric graph driven exclusively by persisted server events.
const NS = 'http://www.w3.org/2000/svg';
const nodes = [
  {name:'Planner Agent', label:'PLAN', x:140,y:120,color:'#c7b8ff'},
  {name:'Data Agent', label:'DATA', x:330,y:65,color:'#8ec9ed'},
  {name:'Policy Agent', label:'POLICY', x:545,y:120,color:'#d5c58d'},
  {name:'Decision Agent', label:'DECIDE', x:470,y:285,color:'#92d8b7'},
  {name:'Action Agent', label:'ACTION', x:205,y:285,color:'#efaa85'},
  {name:'Orchestrator', label:'ORCHESTRATOR', x:335,y:185,color:'#e1e4ea'}
];
const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export class AgentGraph {
  constructor(host, select) {
    this.host = host;
    this.reduced = matchMedia('(prefers-reduced-motion: reduce)');
    host.innerHTML = `<div class="graph-caption"><span>MESSAGE TOPOLOGY / 01</span><span class="graph-mode">LIVE EVENT SOURCE</span></div>
      <svg viewBox="0 0 680 390" role="group" aria-label="Orchestrator routes work to five specialized agents">
        <defs><pattern id="graph-grid" width="38" height="22" patternUnits="userSpaceOnUse"><path d="M0 11L19 0L38 11L19 22Z" fill="none" stroke="currentColor" stroke-width=".5"/></pattern></defs>
        <path class="graph-ground" d="M25 165L340 5L655 165L340 385Z" fill="url(#graph-grid)"/>
        <g class="graph-edges">${nodes.slice(0,5).map((n,i)=>`<path id="edge-${i}" d="M335 185 Q${n.x} 185 ${n.x} ${n.y}"/>`).join('')}</g>
        <g class="packet-layer"></g>
        ${nodes.map((n,i)=>`<g class="spatial-node idle" data-node="${i}" transform="translate(${n.x} ${n.y})" style="--node-color:${n.color}" ${i<5?`role="button" tabindex="0" aria-label="Inspect ${n.name}"`:'role="img" aria-label="Orchestrator"'}>
          <title>${n.name}</title><ellipse class="node-shadow" cy="32" rx="51" ry="17"/>
          <g class="node-object"><path class="node-side-left" d="M-44 0L0 25L0 38L-44 13Z"/>
          <path class="node-side-right" d="M0 25L44 0L44 13L0 38Z"/><path class="node-top" d="M0-25L44 0L0 25L-44 0Z"/>
          <path class="node-inset" d="M0-13L23 0L0 13L-23 0Z"/><text class="node-symbol" y="4">${i===5?'O':String(i+1).padStart(2,'0')}</text></g>
          <text class="node-label" y="65">${n.label}</text><text class="node-status" y="82">IDLE</text></g>`).join('')}
      </svg><div class="graph-footnote"><span>Inspect a node to see its inputs and evidence</span><span>HTTP commands · SSE events</span></div>`;
    this.svg = host.querySelector('svg');
    this.elements = [...host.querySelectorAll('[data-node]')];
    const activate = event => { const node = event.target.closest('[data-node]'); if(node && Number(node.dataset.node)<5) select(Number(node.dataset.node)); };
    host.addEventListener('click', activate);
    host.addEventListener('keydown', event => {if(event.key==='Enter'||event.key===' '){if(event.target.closest('[role=button]')){event.preventDefault();activate(event);}}});
    host.addEventListener('pointermove', event => {
      if(this.reduced.matches || event.pointerType==='touch') return;
      const r=host.getBoundingClientRect();
      this.svg.style.transform=`perspective(1000px) rotateX(${-(event.clientY-r.top-r.height/2)/r.height*3}deg) rotateY(${(event.clientX-r.left-r.width/2)/r.width*4}deg)`;
    });
    host.addEventListener('pointerleave',()=>{this.svg.style.transform='';});
  }
  update(states, selected, events, replaying) {
    this.replaying = replaying;
    this.host.querySelector('.graph-mode').textContent = replaying ? 'HISTORICAL REPLAY' : 'LIVE EVENT SOURCE';
    if(replaying) this.host.querySelector('.packet-layer').replaceChildren();
    this.elements.forEach((el,i)=>{
      const state=i<5?states[i].state:states.some(s=>s.state==='running')?'running':states.some(s=>s.state==='failed')?'failed':states.some(s=>s.state==='waiting')?'waiting':events.length?'complete':'idle';
      el.setAttribute('class',`spatial-node ${state} ${i===selected?'selected':''}`);
      el.querySelector('.node-status').textContent=state==='waiting'?'NEEDS APPROVAL':state.toUpperCase();
      if(i<5){
        el.setAttribute('aria-pressed',String(i===selected));
        el.setAttribute('aria-label',`${nodes[i].name}: ${state}. Inspect input and output.`);
        const output=states[i].output;
        el.querySelector('title').textContent=`${nodes[i].name} · ${state}\n${states[i].input?.detail.purpose||'Awaiting task'}\nCompute: ${output?.detail.duration_ms??'—'} ms`;
      }
    });
  }
  packet(message) {
    if(this.replaying || this.reduced.matches) return;
    const from=nodes.findIndex(n=>n.name===message.from), to=nodes.findIndex(n=>n.name===message.to);
    if(from<0||to<0||from===to) return;
    const index=from===5?to:from;
    const path=this.host.querySelector(`#edge-${index}`);
    if(!path) return;
    const layer=this.host.querySelector('.packet-layer');
    // Bound packet count after a reconnect; old packets carry no application state.
    if(layer.childElementCount>=12) layer.firstChild.remove();
    const circle=document.createElementNS(NS,'circle');
    circle.setAttribute('r','3.8');circle.setAttribute('fill',nodes[index].color);layer.append(circle);
    const length=path.getTotalLength(), began=performance.now();
    const animate=now=>{
      if(!circle.isConnected) return;
      const progress=Math.min(1,(now-began)/750), distance=(from===5?progress:1-progress)*length;
      const p=path.getPointAtLength(distance);circle.setAttribute('cx',p.x);circle.setAttribute('cy',p.y);
      if(progress<1) requestAnimationFrame(animate);else circle.remove();
    };
    requestAnimationFrame(animate);
  }
}

export function renderGantt(host, events, agents) {
  const starts=events.filter(e=>e.kind==='agent_started');
  if(!starts.length){host.innerHTML='<p class="gantt-empty">Run a workflow to compare agent execution times.</p>';return;}
  const base=Date.parse(starts[0].created_at);
  const end=Math.max(base+1,...events.map(e=>Date.parse(e.created_at)));
  const total=Math.max(1,end-base);
  host.innerHTML=starts.map(start=>{
    const finish=events.find(e=>e.kind==='agent_completed' && e.agent===start.agent && e.id>start.id && (!start.detail.step_id||e.detail.step_id===start.detail.step_id));
    const offset=Math.max(0,Date.parse(start.created_at)-base), duration=finish?Math.max(1,Date.parse(finish.created_at)-Date.parse(start.created_at)):Math.max(1,end-Date.parse(start.created_at));
    const color=nodes.find(n=>n.name===start.agent)?.color||'#bfc7ce';
    return `<div class="gantt-row"><span>${safe(start.agent.replace(' Agent',''))}</span><div class="gantt-track"><i style="--bar-color:${color};left:${offset/total*100}%;width:${Math.max(.6,Math.min(100-offset/total*100,duration/total*100))}%"></i></div><code>${finish?safe(finish.detail.duration_ms)+' ms':'…'}</code></div>`;
  }).join('')+'<p class="gantt-note">Bars show elapsed wall time, including presentation pace. Labels show measured compute time.</p>';
}
