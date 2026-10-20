/** Real HTTP + SSE integration in a DOM emulator. No layout/GPU claim. */
import assert from 'node:assert/strict';
import {readFile,mkdtemp,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {Window} from 'happy-dom';
const root=new URL('../',import.meta.url),temp=await mkdtemp(join(tmpdir(),'orchestra-final-ui-'));
const port=8768,origin=`http://127.0.0.1:${port}`;
const executable=process.env.ORCHESTRA_PYTHON||(process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const server=spawn(executable,['-m','uvicorn','app.main:app','--host','127.0.0.1','--port',String(port)],{cwd:root,env:{...process.env,ORCHESTRA_LEGACY:'0',AGENTFLOW_DB:join(temp,'test.db'),GEMINI_API_KEY:''},stdio:['ignore','pipe','pipe']});
let log='',cookie='',streamEvents=0;server.stdout.on('data',b=>log+=b);server.stderr.on('data',b=>log+=b);
const window=new Window({url:origin,settings:{disableJavaScriptFileLoading:true,disableCSSFileLoading:true}});
const $=s=>window.document.querySelector(s),sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<600;i++){if(await fn())return;await sleep(20)}throw new Error('Timeout: '+label+'\nTOAST '+$('#toast')?.textContent+'\nAUTH '+$('#auth-error')?.textContent+'\n'+log.slice(-4000))}
async function http(path,options={}){const response=await fetch(new URL(path,origin),{...options,headers:{...options.headers,...(cookie?{cookie}:{})}});const set=response.headers.get('set-cookie');if(set)cookie=set.split(';')[0];return response}
class Stream{constructor(path){this.abort=new AbortController();this.read(path)}async read(path){try{const response=await http(path,{signal:this.abort.signal});assert.equal(response.status,200);let buffer='';for await(const bytes of response.body){buffer+=new TextDecoder().decode(bytes);let i;while((i=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,i);buffer=buffer.slice(i+2);const data=block.split('\n').find(l=>l.startsWith('data: '));if(data){streamEvents++;this.onmessage?.({data:data.slice(6)})}}}}catch(e){if(e.name!=='AbortError'){log+=e.stack;this.onerror?.()}}}close(){this.abort.abort()}}
function submit(selector){$(selector).dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}))}
function click(selector){assert.ok($(selector),'Missing '+selector);$(selector).click()}
async function page(id){click(`nav [data-page="${id}"]`);await until(()=>!$('.loading')&&!!$('#page h1'),id+' page')}
const checks=[];
try{
 await until(async()=>{try{return(await http('/api/health')).ok}catch{return false}},'backend');
 window.fetch=http;window.EventSource=Stream;window.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}});
 const html=(await readFile(new URL('static/workspace.html',root),'utf8')).replace(/<script[\s\S]*?<\/script>/g,'');window.document.write(html);
 const spatial=(await readFile(new URL('static/spatial.js',root),'utf8')).replaceAll('export const ','const ').replaceAll('export class ','class ');
 const consoleCode=(await readFile(new URL('static/console.js',root),'utf8')).replace(/^import[^\n]+\n/,'');
 window.eval('(async()=>{'+spatial+'\n'+consoleCode+'})().catch(e=>{document.body.dataset.testError=e.stack})');
 await until(()=>!$('#auth').hidden,'auth');click('#auth-toggle');$('#auth-form [name=email]').value='ui@example.com';$('#auth-form [name=password]').value='correct-horse-42';submit('#auth-form');
 await until(()=>!!$('#company-form'),'company form');$('#company-form input').value='UI Test SME';submit('#company-form');
 await until(()=>!!$('[data-action=seed]'),'overview');checks.push('Registration and workspace creation through forms');
 click('[data-action=seed]');await until(()=>$('#page').textContent.includes('1,180')||$('#page').textContent.includes('1,180'),'demo seeded');
 assert.equal(window.document.querySelectorAll('[data-agent]').length,8);checks.push('Eight interactive graph nodes');
 click('[data-action=run]');await until(()=>$('#feed')?.textContent.includes('run done'),'weekly SSE complete');assert.ok(streamEvents>20);assert.ok($('.timeline-row'));checks.push('Real SSE, agent states and measured timeline');
 $('[data-agent=Auditor]').dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));assert.match($('#inspector').textContent,/Auditor/);checks.push('Keyboard agent inspection');
 await page('reports');assert.match($('#page').textContent,/published/);const pdf=$('a[download]').getAttribute('href');assert.equal((await http(pdf)).headers.get('content-type'),'application/pdf');checks.push('Audited report and downloadable PDF');
 await page('issues');click('[data-action=quick-scan]');await until(()=>$('#feed')?.textContent.includes('run done'),'scan complete');await page('issues');
 const refund=[...window.document.querySelectorAll('.issue')].find(i=>i.textContent.includes('Refund:'));assert.ok(refund);refund.querySelector('button').click();await until(()=>!!$('[data-action=approve]'),'approval preview');click('[data-action=approve]');await until(()=>$('#toast').textContent.includes('verified'),'approval result');checks.push('Record and policy evidence before simulated refund approval');
 await page('ask');$('#ask-form textarea').value='refund manager approval 5000';submit('#ask-form');await until(()=>!!$('#answer [data-action=source]'),'cited answer');click('#answer [data-action=source]');await until(()=>$('#modal-content').textContent.includes('Refund approvals'),'source viewer');click('#modal-close');checks.push('Cited Q&A and source viewer');
 await page('policies');$('#policy-form [name=refund_threshold]').value='10000';click('[data-action=simulate]');await until(()=>$('#simulation-result').textContent.includes('Impact comparison'),'policy simulation');assert.match($('#simulation-result').textContent,/decisions change/);checks.push('Side-by-side policy impact');
 await page('evaluation');click('[data-action=evaluate]');await until(()=>$('#page').textContent.includes('100%'),'evaluation result');checks.push('Measured evaluation screen');
 await page('runs');click('[data-action=replay]');await until(()=>$('#toast').textContent.includes('Replay finished'),'replay');checks.push('Persisted read-only event replay');
 click('#theme');assert.equal(window.document.documentElement.dataset.theme,'light');$('#command-open').click();assert.ok($('#commands').open);$('#command-close').click();checks.push('Theme and command palette');
 for(const id of ['data','knowledge','audit']){await page(id);assert.ok(!$('#page').textContent.includes('Could not load'));}checks.push('All ten page routes render');
 assert.ok(!window.document.body.dataset.testError,window.document.body.dataset.testError);
 const report={status:'passed',checks,streamEvents,limitation:'DOM/API emulator; no actual browser screenshot, responsive pixel layout, CSS animation frames or GPU rendering verified.'};
 console.log(JSON.stringify(report,null,2));await writeFile(new URL('docs/final-ui-verification.json',root),JSON.stringify(report,null,2)+'\n');
}finally{await window.happyDOM.abort();server.kill();await new Promise(r=>server.exitCode!==null?r():server.once('exit',r));await rm(temp,{recursive:true,force:true})}
