/** DOM/API integration, not a real browser, layout or GPU-rendering test.
 * Starts a disposable backend; no user database is modified.
 * Run with ORCHESTRA_PYTHON pointing to the project's venv Python if needed.
 */
import assert from 'node:assert/strict';
import {readFile, mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {Window} from 'happy-dom';

const root=new URL('../',import.meta.url);
const temp=await mkdtemp(join(tmpdir(),'orchestra-ui-'));
const port=Number(process.env.ORCHESTRA_TEST_PORT||8767);
const origin=`http://127.0.0.1:${port}`;
const executable=process.env.ORCHESTRA_PYTHON||(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const server=spawn(executable,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port',String(port)],
  {cwd:root,env:{...process.env,AGENTFLOW_DB:join(temp,'test.db'),GEMINI_API_KEY:'',ORCHESTRA_LEGACY:'1'},stdio:['ignore','pipe','pipe']});
let serverLog='';server.stdout.on('data',b=>serverLog+=b);server.stderr.on('data',b=>serverLog+=b);
server.on('error',error=>serverLog+=error.message);
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(predicate,label){for(let i=0;i<250;i++){if(await predicate())return;await sleep(20);}throw new Error(`Timed out: ${label}; status=${window.document.getElementById("run-status")?.textContent}; error=${window.document.getElementById("error")?.textContent}; response=${window.document.getElementById("result-response")?.textContent}\n${serverLog}`);}
const window=new Window({url:origin,settings:{disableJavaScriptFileLoading:true,disableCSSFileLoading:true}});
let streamCount=0;
class Stream {
  constructor(path){this.controller=new AbortController();this.read(path);}
  async read(path){try{
    const response=await fetch(new URL(path,origin),{signal:this.controller.signal});
    assert.equal(response.status,200);this.onopen?.();
    let buffer='';const decoder=new TextDecoder();
    for await(const bytes of response.body){buffer+=decoder.decode(bytes,{stream:true});let index;
      while((index=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,index);buffer=buffer.slice(index+2);
        const data=block.split('\n').find(line=>line.startsWith('data: '));
        if(data){streamCount++;this.onmessage?.({data:data.slice(6)});}
      }
    }
  }catch(error){if(error.name!=='AbortError'){this.onerror?.();serverLog+=error.stack;}}}
  close(){this.controller.abort();}
}
try{
  await until(async()=>{try{return (await fetch(origin+'/api/health')).ok;}catch{return false;}},'backend startup');
  window.fetch=(path,options)=>fetch(new URL(path,origin),options);
  window.EventSource=Stream;
  window.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}});
  const html=(await readFile(new URL('static/index.html',root),'utf8')).replace(/<script[\s\S]*?<\/script>/g,'');
  window.document.write(html);
  const graph=(await readFile(new URL('static/graph.js',root),'utf8')).replaceAll('export class ','class ').replaceAll('export function ','function ');
  const app=(await readFile(new URL('static/app.js',root),'utf8')).replace(/^import[^\n]+\n/,'');
  window.eval(graph+'\n'+app);
  const $=id=>window.document.getElementById(id);
  await until(()=>$('order').options.length===8,'order options loaded');
  assert.equal(window.document.querySelectorAll('.spatial-node').length,6);
  assert.equal($('error').hidden,true,$('error').textContent);
  window.document.querySelector('[data-scenario="cancel"]').click();
  assert.equal($('intent').value,'cancel');
  $('guided').checked=false;
  $('run-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
  await until(()=>$('run-status').textContent==='WAITING FOR YOU'&&!$('run').disabled,'approval checkpoint');
  assert.match($('timeline').textContent,/Orchestrator → Planner Agent/);
  assert.match($('spatial-graph').textContent,/NEEDS APPROVAL/);
  assert.equal($('gantt').querySelectorAll('.gantt-row').length,4);
  assert.ok(streamCount>0,'Actual SSE events consumed');
  const before=await(await fetch(origin+'/api/orders/ORD-1001')).json();assert.equal(before.version,1);
  window.document.querySelector('[data-node="2"]').dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert.equal($('inspector-title').textContent,'Policy Agent');
  $('reviewer').value='UI smoke reviewer';
  $('review-form').dispatchEvent(new window.SubmitEvent('submit',{bubbles:true,cancelable:true,
    submitter:window.document.querySelector('[value="approve"]')}));
  await until(()=>$('run-status').textContent==='completed'&&!$('run').disabled,'approved mutation');
  assert.match($('result-response').textContent,/Cancellation completed/);
  $('replay-toggle').click();
  assert.equal($('run-status').textContent,'HISTORICAL REPLAY');
  assert.equal(window.document.querySelector('[value="approve"]').disabled,true);
  $('step-next').click();$('theme-toggle').click();
  assert.equal(window.document.documentElement.dataset.theme,'light');
  assert.equal($('error').hidden,true,$('error').textContent);
  const after=await(await fetch(origin+'/api/orders/ORD-1001')).json();assert.equal(after.version,2);
  assert.equal((await(await fetch(origin+'/api/metrics')).json()).refunds,1);
  console.log(JSON.stringify({status:'passed',checks:['DOM initialization','actual SSE rendering','approval wait','3D graph state','keyboard node inspection','measured timeline','approved mutation','read-only replay','theme toggle'],streamEvents:streamCount,limitation:'No real browser, visual layout, animation frames or GPU rendering verified.'},null,2));
}finally{
  await window.happyDOM.abort();
  server.kill();
  await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  await rm(temp,{recursive:true,force:true});
}
