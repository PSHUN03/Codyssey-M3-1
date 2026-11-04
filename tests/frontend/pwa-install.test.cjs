const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const code=fs.readFileSync(path.join(__dirname,'../../app/static/js/app.js'),'utf8');
const installCode=code.slice(code.indexOf('function initPwaInstall()'));
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function setup({ios=false,desktop=false,secure=true,standalone=false,secondary=false}={}){
  const button=new EventTarget();Object.assign(button,{hidden:true,disabled:false,attributes:{},setAttribute(key,value){this.attributes[key]=value;}});
  const media=new EventTarget();media.matches=standalone;
  const title={},description={},panels=['ios','ios','android','android'].map(kind=>({dataset:{pwaGuide:kind},hidden:kind==='android'}));
  const dialog={open:false,showModal(){this.open=true;},close(){this.open=false;},querySelector(selector){return selector==='#pwa-install-title'?title:description;},querySelectorAll(){return panels;}};
  const classes=new Set(),window=new EventTarget();Object.assign(window,{isSecureContext:secure,matchMedia:()=>media});
  const document={querySelector(selector){if(selector==='#pwa-install-button')return button;if(selector==='#pwa-install-dialog')return dialog;return secondary?{}:null;},documentElement:{classList:{toggle(key,enabled){if(enabled)classes.add(key);else classes.delete(key);}}}};
  const navigator={userAgent:desktop?'Desktop Chrome':ios?'iPhone Safari':'Android Chrome',platform:'',maxTouchPoints:0,standalone:false};
  const messages=[];vm.runInNewContext(installCode,{window,document,navigator,toast:message=>messages.push(message)});
  const event=(prompt,choice)=>{const event=new Event('beforeinstallprompt',{cancelable:true});event.prompt=prompt;event.userChoice=Promise.resolve({outcome:choice||'dismissed'});window.dispatchEvent(event);return event;};
  return {button,dialog,title,description,panels,window,media,classes,messages,event,click:async()=>{button.dispatchEvent(new Event('click'));await settle();}};
}
test('Android without a native install event still has the same header guide action',async()=>{
  const ui=setup({secondary:true});assert.equal(ui.button.hidden,false);assert.equal(ui.button.textContent,'설치 안내');assert.equal(ui.classes.has('has-pwa-install-secondary'),true);
  await ui.click();assert.equal(ui.dialog.open,true);assert.equal(ui.title.textContent,'Chrome에서 추가해요');assert.ok(ui.panels.filter(panel=>panel.dataset.pwaGuide==='ios').every(panel=>panel.hidden));
});
test('iPhone keeps its Safari guide and ignores synthetic native-install events',async()=>{
  const ui=setup({ios:true});let calls=0;const event=ui.event(async()=>calls++);assert.equal(event.defaultPrevented,false);
  await ui.click();assert.equal(calls,0);assert.equal(ui.title.textContent,'홈 화면에 추가해요');assert.ok(ui.panels.filter(panel=>panel.dataset.pwaGuide==='android').every(panel=>panel.hidden));
});
test('native prompt is used once and cancelling leaves a guide without reopening a modal',async()=>{
  const ui=setup();let calls=0;const event=ui.event(async()=>calls++,'dismissed');assert.equal(event.defaultPrevented,true);assert.equal(ui.button.textContent,'앱 설치');
  await ui.click();assert.equal(calls,1);assert.equal(ui.button.textContent,'설치 안내');assert.equal(ui.dialog.open,false);await ui.click();assert.equal(calls,1);assert.equal(ui.dialog.open,true);
});
test('failed native prompt falls back to the Android menu guide and releases the button',async()=>{
  const ui=setup();ui.event(async()=>{throw new Error('unsupported');});await ui.click();assert.equal(ui.dialog.open,true);assert.equal(ui.button.disabled,false);assert.equal(ui.title.textContent,'Chrome에서 추가해요');
});
test('double clicks cannot reuse a pending native event and appinstalled hides its guide',async()=>{
  const ui=setup();let release,calls=0;const pending=new Promise(resolve=>release=resolve);ui.event(async()=>{calls++;await pending;},'accepted');
  ui.button.dispatchEvent(new Event('click'));await ui.click();assert.equal(calls,1);assert.equal(ui.button.disabled,true);release();await settle();
  ui.window.dispatchEvent(new Event('appinstalled'));assert.equal(ui.button.hidden,true);assert.equal(ui.classes.has('has-pwa-install'),false);await ui.click();assert.equal(ui.dialog.open,false);
});
test('desktop, standalone and insecure pages stay hidden; desktop native prompts are untouched',()=>{
  for(const options of [{desktop:true},{standalone:true},{secure:false}])assert.equal(setup(options).button.hidden,true);
  const desktop=setup({desktop:true});assert.equal(desktop.event(async()=>{}).defaultPrevented,false);
});
