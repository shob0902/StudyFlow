# Three.js 3D scenes (hero crystal, thinking loader, score celebration, rocket, workflow map) embedded as iframes, in the StudyFlow violet palette.
import json
import streamlit as st
from graph.workflow import (
    EVALUATE_ANSWERS,
    GENERATE_EXAMPLES,
    GENERATE_EXPLANATION,
    GENERATE_QUIZ,
    RE_EXPLAIN_TOPIC,
    RECOMMEND_NEXT_TOPIC,
    UNDERSTAND_TOPIC,
    WAIT_FOR_ANSWERS,
)
THREE_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
START_NODE = "__start__"
END_NODE = "__end__"
WORKFLOW_NODES = [
    (START_NODE, "START", -7.0, 0.0, 0.0),
    (UNDERSTAND_TOPIC, "Understand", -5.0, 0.8, 0.0),
    (GENERATE_EXPLANATION, "Explain", -3.0, -0.4, 0.6),
    (GENERATE_EXAMPLES, "Examples", -1.0, 0.8, -0.4),
    (GENERATE_QUIZ, "Quiz", 1.0, -0.2, 0.4),
    (WAIT_FOR_ANSWERS, "Your answers", 3.0, 0.9, -0.3),
    (EVALUATE_ANSWERS, "Evaluate", 5.0, -0.1, 0.3),
    (RE_EXPLAIN_TOPIC, "Re-explain", 3.0, -2.5, 0.8),
    (RECOMMEND_NEXT_TOPIC, "Next topic", 7.0, 0.9, 0.0),
    (END_NODE, "END", 8.8, 0.0, 0.0),
]
WORKFLOW_EDGES = [
    (START_NODE, UNDERSTAND_TOPIC, "normal"),
    (UNDERSTAND_TOPIC, GENERATE_EXPLANATION, "normal"),
    (GENERATE_EXPLANATION, GENERATE_EXAMPLES, "normal"),
    (GENERATE_EXAMPLES, GENERATE_QUIZ, "normal"),
    (GENERATE_QUIZ, WAIT_FOR_ANSWERS, "normal"),
    (WAIT_FOR_ANSWERS, EVALUATE_ANSWERS, "normal"),
    (EVALUATE_ANSWERS, RE_EXPLAIN_TOPIC, "conditional"),
    (RE_EXPLAIN_TOPIC, GENERATE_QUIZ, "loop"),
    (EVALUATE_ANSWERS, RECOMMEND_NEXT_TOPIC, "conditional"),
    (RECOMMEND_NEXT_TOPIC, END_NODE, "normal"),
]
PAGE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;overflow:hidden;background:transparent;font-family:"Source Sans Pro","Segoe UI",system-ui,-apple-system,sans-serif;color:#17152B;}
#stage{position:absolute;inset:0;}
.fallback{display:none;position:absolute;inset:0;align-items:center;justify-content:center;perspective:600px;}
.no3d .fallback{display:flex;}
.cube{width:70px;height:70px;position:relative;transform-style:preserve-3d;animation:cubeSpin 7s linear infinite;}
.cube div{position:absolute;inset:0;border-radius:12px;background:rgba(109,74,255,.9);border:2px solid #5535D9;display:grid;place-items:center;font-size:30px;}
.cube .f1{transform:translateZ(35px)}.cube .f2{transform:rotateY(180deg) translateZ(35px)}.cube .f3{transform:rotateY(90deg) translateZ(35px)}.cube .f4{transform:rotateY(-90deg) translateZ(35px)}.cube .f5{transform:rotateX(90deg) translateZ(35px)}.cube .f6{transform:rotateX(-90deg) translateZ(35px)}
@keyframes cubeSpin{to{transform:rotateX(360deg) rotateY(360deg)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
__CSS__
</style></head><body>
__BODY__
<div class="fallback"><div class="cube"><div class="f1"></div><div class="f2"></div><div class="f3"></div><div class="f4"></div><div class="f5"></div><div class="f6"></div></div></div>
<script src="__THREE__"></script>
<script>
const REDUCE=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function makeStage(el,fov,z,fitWidth){const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setClearColor(0x000000,0);el.appendChild(renderer.domElement);const scene=new THREE.Scene();const camera=new THREE.PerspectiveCamera(fov,1,0.1,200);camera.position.set(0,0,z);scene.add(new THREE.AmbientLight(0xffffff,0.8));const sun=new THREE.DirectionalLight(0xffffff,0.85);sun.position.set(4,6,8);scene.add(sun);const rim=new THREE.PointLight(0xA99BFF,0.8,40);rim.position.set(-5,-3,4);scene.add(rim);function resize(){const w=Math.max(el.clientWidth,1),h=Math.max(el.clientHeight,1);renderer.setSize(w,h);camera.aspect=w/h;if(fitWidth){camera.position.z=Math.max(z,fitWidth/2/(Math.tan(fov*Math.PI/360)*camera.aspect));}camera.updateProjectionMatrix();}window.addEventListener("resize",resize);if(window.ResizeObserver){new ResizeObserver(resize).observe(el);}resize();return {el:el,renderer:renderer,scene:scene,camera:camera};}
function animate(stage,update){const clock=new THREE.Clock();function frame(){const t=REDUCE?2:clock.getElapsedTime();if(stage.el.clientWidth>0){update(t);stage.renderer.render(stage.scene,stage.camera);}if(!REDUCE){requestAnimationFrame(frame);}}frame();}
function mat(color,extra){return new THREE.MeshStandardMaterial(Object.assign({color:color,roughness:0.5,metalness:0.1,flatShading:true},extra||{}));}
function dust(scene,count,spread,color,size){const pos=new Float32Array(count*3);for(let i=0;i<count;i++){pos[i*3]=(Math.random()-0.5)*spread[0];pos[i*3+1]=(Math.random()-0.5)*spread[1];pos[i*3+2]=(Math.random()-0.5)*spread[2];}const g=new THREE.BufferGeometry();g.setAttribute("position",new THREE.BufferAttribute(pos,3));const p=new THREE.Points(g,new THREE.PointsMaterial({color:color,size:size,transparent:true,opacity:0.75}));scene.add(p);return p;}
__PRE__
function start(){
__SCRIPT__
}
if(window.THREE){try{start();}catch(err){console.error(err);document.body.classList.add("no3d");}}else{document.body.classList.add("no3d");}
</script></body></html>"""
HERO_SCRIPT = """
const s=makeStage(document.getElementById("stage"),45,7,7.5);
const crystal=new THREE.Group();s.scene.add(crystal);
const core=new THREE.Mesh(new THREE.IcosahedronGeometry(1.25,0),mat(0x6D4AFF,{metalness:0.2,roughness:0.4}));crystal.add(core);
const inner=new THREE.Mesh(new THREE.OctahedronGeometry(0.55,0),mat(0xF2B544,{emissive:0xF2B544,emissiveIntensity:0.35}));crystal.add(inner);
const shell=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(1.7,1)),new THREE.LineBasicMaterial({color:0x5535D9,transparent:true,opacity:0.45}));crystal.add(shell);
const ring=new THREE.Mesh(new THREE.TorusGeometry(2.35,0.035,12,140),mat(0xA99BFF,{flatShading:false}));ring.rotation.x=1.2;s.scene.add(ring);
const palette=[0x5535D9,0x6D4AFF,0xA99BFF,0xF2B544];const orbiters=[];
for(let i=0;i<8;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(0.15,20,20),mat(palette[i%4],{flatShading:false,emissive:palette[i%4],emissiveIntensity:0.25}));s.scene.add(m);orbiters.push(m);}
const specks=dust(s.scene,170,[14,8,6],0x6D4AFF,0.05);
let mx=0,my=0;window.addEventListener("pointermove",function(e){mx=e.clientX/window.innerWidth-0.5;my=e.clientY/window.innerHeight-0.5;});
animate(s,function(t){crystal.rotation.y=t*0.5;crystal.rotation.x=Math.sin(t*0.4)*0.3;crystal.position.y=Math.sin(t*1.2)*0.12;inner.rotation.y=-t*1.4;inner.rotation.z=t*0.8;shell.rotation.y=-t*0.25;ring.rotation.z=t*0.2;orbiters.forEach(function(m,i){const a=t*0.8+i*Math.PI/4;const r=2.35;m.position.set(Math.cos(a)*r,Math.sin(a)*r*Math.cos(1.2),Math.sin(a)*r*Math.sin(1.2));});specks.rotation.y=t*0.03;s.camera.position.x+=(mx*1.4-s.camera.position.x)*0.05;s.camera.position.y+=(-my*1.0-s.camera.position.y)*0.05;s.camera.lookAt(0,0,0);});
"""
THINKING_CSS = """
.caption{position:absolute;left:0;right:0;bottom:10px;text-align:center;font-weight:800;font-size:15px;}
.caption span{display:inline-block;animation:bounce 1.2s infinite;}
.caption span:nth-child(2){animation-delay:.15s}.caption span:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-4px);opacity:1}}
"""
THINKING_BODY = """<div id="stage"></div><div class="caption">LangGraph is thinking<span>.</span><span>.</span><span>.</span></div>"""
THINKING_SCRIPT = """
const s=makeStage(document.getElementById("stage"),45,6.5,6);
const knot=new THREE.Mesh(new THREE.TorusKnotGeometry(0.95,0.28,160,18),mat(0x6D4AFF,{flatShading:false,roughness:0.3,metalness:0.3}));knot.position.y=0.25;s.scene.add(knot);
const cage=new THREE.Mesh(new THREE.TorusKnotGeometry(0.95,0.34,70,10),new THREE.MeshBasicMaterial({color:0x5535D9,wireframe:true,transparent:true,opacity:0.22}));cage.position.y=0.25;s.scene.add(cage);
const cubes=[];[0xA99BFF,0xF2B544,0x5535D9].forEach(function(c){const m=new THREE.Mesh(new THREE.BoxGeometry(0.32,0.32,0.32),mat(c));s.scene.add(m);cubes.push(m);});
animate(s,function(t){knot.rotation.x=t*0.7;knot.rotation.y=t*0.9;cage.rotation.copy(knot.rotation);const k=1+Math.sin(t*3)*0.05;knot.scale.set(k,k,k);cubes.forEach(function(c,i){const a=t*1.6+i*2.094;c.position.set(Math.cos(a)*2.2,0.25+Math.sin(a*1.3)*0.5,Math.sin(a)*2.2);c.rotation.x=t*2;c.rotation.y=t*1.5;});});
"""
SCORE_CSS = """
.wrap{position:absolute;inset:0;display:flex;align-items:center;}
.ring{position:relative;width:210px;min-width:170px;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;}
.ring svg{width:160px;height:160px;transform:rotate(-90deg);}
.ring .num{position:absolute;top:50%;left:50%;transform:translate(-50%,-62%);font-size:38px;font-weight:900;}
.ring .cap{margin-top:6px;font-weight:800;font-size:15px;}
.scene{position:relative;flex:1;height:100%;}
.fallback{left:210px;}
"""
SCORE_PRE = """
const TARGET=__SCORE__;const C=2*Math.PI*70;const arc=document.getElementById("arc");const num=document.getElementById("num");arc.style.strokeDasharray=C;arc.style.strokeDashoffset=C;
const t0=performance.now();function tick(now){const p=REDUCE?1:Math.min((now-t0)/1500,1);const e=1-Math.pow(1-p,3);num.textContent=Math.round(TARGET*e)+"%";arc.style.strokeDashoffset=C*(1-TARGET/100*e);if(p<1){requestAnimationFrame(tick);}}requestAnimationFrame(tick);
"""
TROPHY_SCRIPT = """
const s=makeStage(document.getElementById("stage"),40,7.5,6);
const gold=mat(0xF2B544,{flatShading:false,metalness:0.55,roughness:0.28});
const trophy=new THREE.Group();
const cup=new THREE.Mesh(new THREE.CylinderGeometry(1,0.5,1.3,40,1,true),mat(0xF2B544,{flatShading:false,metalness:0.55,roughness:0.28,side:THREE.DoubleSide}));cup.position.y=0.9;trophy.add(cup);
const lip=new THREE.Mesh(new THREE.TorusGeometry(1,0.07,12,48),gold);lip.rotation.x=Math.PI/2;lip.position.y=1.55;trophy.add(lip);
[-1,1].forEach(function(side){const h=new THREE.Mesh(new THREE.TorusGeometry(0.38,0.08,12,32,Math.PI),gold);h.position.set(side*0.95,1.0,0);h.rotation.z=side>0?-Math.PI/2:Math.PI/2;trophy.add(h);});
const stem=new THREE.Mesh(new THREE.CylinderGeometry(0.14,0.22,0.7,20),gold);stem.position.y=-0.05;trophy.add(stem);
const base=new THREE.Mesh(new THREE.BoxGeometry(1.3,0.3,1.3),mat(0x5535D9,{flatShading:false,roughness:0.4}));base.position.y=-0.55;trophy.add(base);
const star=new THREE.Mesh(new THREE.OctahedronGeometry(0.28,0),mat(0xFFFFFF,{emissive:0xF2B544,emissiveIntensity:0.7}));star.position.y=2.15;trophy.add(star);
trophy.position.y=-0.6;s.scene.add(trophy);
const colors=[0x5535D9,0x6D4AFF,0xA99BFF,0xF2B544,0xD96C4F];const bits=[];
for(let i=0;i<90;i++){const b=new THREE.Mesh(new THREE.PlaneGeometry(0.12,0.2),new THREE.MeshBasicMaterial({color:colors[i%5],side:THREE.DoubleSide}));b.position.set((Math.random()-0.5)*7,Math.random()*6-2.5,(Math.random()-0.5)*3);b.userData={v:0.6+Math.random()*1.2,r:Math.random()*4};s.scene.add(b);bits.push(b);}
let last=0;
animate(s,function(t){const dt=Math.min(Math.max(t-last,0),0.05);last=t;const intro=Math.min(t/0.9,1);const e=1-Math.pow(1-intro,3);trophy.scale.setScalar(0.3+0.7*e);trophy.rotation.y=t*0.9;trophy.position.y=-0.6+Math.sin(t*2)*0.08;star.rotation.y=t*3;bits.forEach(function(b){b.position.y-=b.userData.v*dt;b.rotation.x+=b.userData.r*dt;b.rotation.y+=b.userData.r*dt*0.7;if(b.position.y<-3.2){b.position.y=3.5;b.position.x=(Math.random()-0.5)*7;}});});
"""
SEEDLING_SCRIPT = """
const s=makeStage(document.getElementById("stage"),40,7,5);
const plant=new THREE.Group();plant.position.y=-1.3;s.scene.add(plant);
const pot=new THREE.Mesh(new THREE.CylinderGeometry(0.9,0.65,0.9,32),mat(0xB5774B,{flatShading:false,roughness:0.8}));plant.add(pot);
const potRim=new THREE.Mesh(new THREE.TorusGeometry(0.9,0.09,12,40),mat(0xC98A5B,{flatShading:false}));potRim.rotation.x=Math.PI/2;potRim.position.y=0.45;plant.add(potRim);
const soil=new THREE.Mesh(new THREE.CylinderGeometry(0.84,0.84,0.08,32),mat(0x5B4230));soil.position.y=0.42;plant.add(soil);
const stemGeo=new THREE.CylinderGeometry(0.06,0.08,1.6,12);stemGeo.translate(0,0.8,0);const stem=new THREE.Mesh(stemGeo,mat(0x5535D9,{flatShading:false}));stem.position.y=0.45;plant.add(stem);
function leaf(side){const g=new THREE.SphereGeometry(0.45,20,12);g.scale(1,0.18,0.55);g.translate(side*0.45,0,0);const m=new THREE.Mesh(g,mat(0x6D4AFF,{flatShading:false,roughness:0.4}));m.position.y=1.55;plant.add(m);return m;}
const leaves=[leaf(1),leaf(-1)];
const bud=new THREE.Mesh(new THREE.SphereGeometry(0.16,16,16),mat(0xA99BFF,{flatShading:false,emissive:0xA99BFF,emissiveIntensity:0.35}));bud.position.y=2.05;plant.add(bud);
const sparkles=dust(s.scene,45,[5,5,2],0xF2B544,0.08);const sp=sparkles.geometry.attributes.position;
let last=0;
animate(s,function(t){const dt=Math.min(Math.max(t-last,0),0.05);last=t;const g1=Math.min(t/1.2,1),g2=Math.min(Math.max((t-1)/0.8,0),1),g3=Math.min(Math.max((t-1.6)/0.5,0),1);stem.scale.y=Math.max(g1,0.001);leaves.forEach(function(l){l.scale.setScalar(Math.max(g2,0.001));});bud.scale.setScalar(Math.max(g3,0.001));leaves[0].rotation.z=0.35+Math.sin(t*2)*0.08;leaves[1].rotation.z=-0.35-Math.sin(t*2)*0.08;plant.rotation.y=Math.sin(t*0.8)*0.5;plant.rotation.z=Math.sin(t*1.5)*0.04;for(let i=0;i<sp.count;i++){let y=sp.getY(i)+dt*0.6;if(y>2.5){y=-2.5;}sp.setY(i,y);}sp.needsUpdate=true;});
"""
ROCKET_SCRIPT = """
const s=makeStage(document.getElementById("stage"),40,8,5);
const rocket=new THREE.Group();rocket.rotation.z=-0.35;s.scene.add(rocket);
const body=new THREE.Mesh(new THREE.CylinderGeometry(0.55,0.6,2.2,32),mat(0xFFFFFF,{flatShading:false,roughness:0.35}));rocket.add(body);
const nose=new THREE.Mesh(new THREE.ConeGeometry(0.55,1,32),mat(0x5535D9,{flatShading:false}));nose.position.y=1.6;rocket.add(nose);
const band=new THREE.Mesh(new THREE.TorusGeometry(0.59,0.06,10,40),mat(0xA99BFF,{flatShading:false}));band.rotation.x=Math.PI/2;band.position.y=-0.6;rocket.add(band);
const glass=new THREE.Mesh(new THREE.SphereGeometry(0.24,24,16),mat(0x9ED3F0,{flatShading:false,metalness:0.3,roughness:0.1}));glass.position.set(0,0.35,0.5);glass.scale.z=0.5;rocket.add(glass);
const glassRim=new THREE.Mesh(new THREE.TorusGeometry(0.26,0.05,10,30),mat(0x6D4AFF,{flatShading:false}));glassRim.position.set(0,0.35,0.55);rocket.add(glassRim);
for(let i=0;i<3;i++){const a=i*2.094;const fin=new THREE.Mesh(new THREE.BoxGeometry(0.08,0.8,0.6),mat(0x6D4AFF));fin.position.set(Math.cos(a)*0.62,-0.9,Math.sin(a)*0.62);fin.rotation.y=Math.PI/2-a;rocket.add(fin);}
const flame=new THREE.Mesh(new THREE.ConeGeometry(0.4,1.1,24),new THREE.MeshBasicMaterial({color:0xF2B544,transparent:true,opacity:0.9}));flame.rotation.x=Math.PI;flame.position.y=-1.65;rocket.add(flame);
const core=new THREE.Mesh(new THREE.ConeGeometry(0.22,0.7,20),new THREE.MeshBasicMaterial({color:0xFFF3C4}));core.rotation.x=Math.PI;core.position.y=-1.45;rocket.add(core);
const stars=dust(s.scene,120,[10,8,4],0x6D4AFF,0.07);const sp=stars.geometry.attributes.position;
let last=0;
animate(s,function(t){const dt=Math.min(Math.max(t-last,0),0.05);last=t;rocket.position.y=Math.sin(t*1.6)*0.18;rocket.rotation.y=t*0.6;const f=1+Math.sin(t*25)*0.12+Math.random()*0.08;flame.scale.set(1,f,1);core.scale.set(1,f*0.9,1);for(let i=0;i<sp.count;i++){let y=sp.getY(i)-dt*2.2;if(y<-4){y=4;}sp.setY(i,y);}sp.needsUpdate=true;});
"""
WORKFLOW_CSS = """
body{background:radial-gradient(circle at 50% 40%,#FFFFFF 0%,#F1EEFF 100%);}
.legend{position:absolute;top:10px;left:12px;display:flex;gap:10px;flex-wrap:wrap;font-size:13px;font-weight:700;background:rgba(255,255,255,.85);padding:6px 10px;border-radius:999px;}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:-1px;}
.hint{position:absolute;bottom:10px;right:14px;font-size:12px;font-weight:700;opacity:.7;}
"""
WORKFLOW_BODY = """<div id="stage"></div>
<div class="legend"><span><i style="background:#5535D9"></i>visited</span><span><i style="background:#F2B544"></i>current</span><span><i style="background:#D9D3F5"></i>not yet</span></div>
<div class="hint">Drag to rotate</div>"""
WORKFLOW_SCRIPT = """
const NODES=__NODES__;const EDGES=__EDGES__;
const s=makeStage(document.getElementById("stage"),42,15,19);
const world=new THREE.Group();world.position.x=-0.9;s.scene.add(world);
const COLORS={done:0x5535D9,current:0xF2B544,todo:0xD9D3F5};const pos={},state={},meshes=[];
function roundRect(g,x,y,w,h,r){g.beginPath();g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath();}
function label(text,st){const c=document.createElement("canvas");c.width=512;c.height=128;const g=c.getContext("2d");g.font="bold 46px Segoe UI, sans-serif";const w=Math.min(g.measureText(text).width+64,500);g.fillStyle=st==="todo"?"rgba(255,255,255,0.92)":(st==="current"?"#F2B544":"#5535D9");roundRect(g,(512-w)/2,20,w,88,44);g.fill();g.fillStyle=st==="done"?"#FFFFFF":"#17152B";g.textAlign="center";g.textBaseline="middle";g.fillText(text,256,66);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),transparent:true,depthTest:false}));sprite.scale.set(3.2,0.8,1);return sprite;}
NODES.forEach(function(n){const v=new THREE.Vector3(n.x,n.y,n.z);pos[n.id]=v;state[n.id]=n.state;const small=n.id==="__start__"||n.id==="__end__";const geo=small?new THREE.OctahedronGeometry(0.38,0):new THREE.IcosahedronGeometry(0.55,1);const current=n.state==="current";const m=new THREE.Mesh(geo,mat(COLORS[n.state],{emissive:current?0xF2B544:0x000000,emissiveIntensity:current?0.45:0}));m.position.copy(v);m.userData={baseY:n.y,current:current};world.add(m);meshes.push(m);const l=label(n.label,n.state);l.position.set(n.x,n.y+(small?0.85:1.1),n.z);world.add(l);if(current){const halo=new THREE.Mesh(new THREE.TorusGeometry(0.9,0.05,10,50),new THREE.MeshBasicMaterial({color:0xF2B544,transparent:true,opacity:0.85}));halo.position.copy(v);world.add(halo);m.userData.halo=halo;}});
const flows=[];
EDGES.forEach(function(e){const a=pos[e.from],b=pos[e.to];if(!a||!b){return;}const mid=a.clone().add(b).multiplyScalar(0.5);if(e.kind==="loop"){mid.z+=1.8;mid.y-=0.3;}else{mid.y+=0.6;}const curve=new THREE.QuadraticBezierCurve3(a,mid,b);const done=state[e.from]!=="todo"&&state[e.to]!=="todo";const color=done?0x6D4AFF:(e.kind==="normal"?0xDCD6F7:0xF4D58D);world.add(new THREE.Mesh(new THREE.TubeGeometry(curve,40,done?0.06:0.035,8,false),new THREE.MeshStandardMaterial({color:color,roughness:0.6})));const tip=new THREE.Mesh(new THREE.ConeGeometry(0.14,0.35,12),new THREE.MeshStandardMaterial({color:color}));tip.position.copy(curve.getPoint(0.8));tip.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),curve.getTangent(0.8).normalize());world.add(tip);if(done){for(let k=0;k<2;k++){const p=new THREE.Mesh(new THREE.SphereGeometry(0.09,10,10),new THREE.MeshBasicMaterial({color:0xF2B544}));world.add(p);flows.push({p:p,curve:curve,offset:k*0.5});}}});
let dragging=false,px=0,py=0,rotY=-0.22,rotX=0.12;const cv=s.renderer.domElement;cv.style.cursor="grab";cv.style.touchAction="pan-y";
cv.addEventListener("pointerdown",function(e){dragging=true;px=e.clientX;py=e.clientY;cv.style.cursor="grabbing";cv.setPointerCapture(e.pointerId);});
cv.addEventListener("pointermove",function(e){if(!dragging){return;}rotY+=(e.clientX-px)*0.008;rotX=Math.max(-0.6,Math.min(0.6,rotX+(e.clientY-py)*0.005));px=e.clientX;py=e.clientY;});
function release(){dragging=false;cv.style.cursor="grab";}cv.addEventListener("pointerup",release);cv.addEventListener("pointercancel",release);
animate(s,function(t){world.rotation.y=rotY+(dragging?0:Math.sin(t*0.35)*0.18);world.rotation.x=rotX;meshes.forEach(function(m,i){m.rotation.y=t*0.6+i;m.position.y=m.userData.baseY+Math.sin(t*1.4+i)*0.06;if(m.userData.current){const k=1+Math.sin(t*4)*0.12;m.scale.set(k,k,k);m.userData.halo.rotation.x=t*1.5;m.userData.halo.rotation.y=t;m.userData.halo.position.y=m.position.y;}});flows.forEach(function(f){f.p.position.copy(f.curve.getPoint((t*0.35+f.offset)%1));});});
"""
# Fill the shared page template with a scene's CSS, body markup and scripts.
def build_page(script: str, body: str = '<div id="stage"></div>', css: str = "", pre: str = "") -> str:
    return (
        PAGE_TEMPLATE.replace("__CSS__", css)
        .replace("__BODY__", body)
        .replace("__THREE__", THREE_JS_URL)
        .replace("__PRE__", pre)
        .replace("__SCRIPT__", script)
    )
# Show trusted scene HTML in an iframe (st.iframe, or components.html on older Streamlit).
def embed(markup: str, height: int) -> None:
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(markup, height=height)
# Hero scene: a floating knowledge crystal with orbiting nodes that follows the mouse.
def hero_scene() -> str:
    return build_page(HERO_SCRIPT)
# Loader scene shown while LangGraph runs: a spinning torus knot with orbiting cubes.
def thinking_scene() -> str:
    return build_page(THINKING_SCRIPT, body=THINKING_BODY, css=THINKING_CSS)
# Score scene: an animated score ring plus a spinning trophy (pass) or a growing seedling (retry).
def score_scene(score: float, passed: bool) -> str:
    color = "#5535D9" if passed else "#F2B544"
    caption = "Level up!" if passed else "Keep growing"
    body = (
        '<div class="wrap"><div class="ring">'
        '<svg viewBox="0 0 160 160"><circle cx="80" cy="80" r="70" fill="none" stroke="#ECE8FB" stroke-width="14"/>'
        f'<circle id="arc" cx="80" cy="80" r="70" fill="none" stroke="{color}" stroke-width="14" stroke-linecap="round"/></svg>'
        f'<div class="num" id="num">0%</div><div class="cap">{caption}</div></div>'
        '<div class="scene"><div id="stage"></div></div></div>'
    )
    pre = SCORE_PRE.replace("__SCORE__", str(round(max(0.0, min(100.0, float(score))))))
    return build_page(TROPHY_SCRIPT if passed else SEEDLING_SCRIPT, body=body, css=SCORE_CSS, pre=pre)
# Rocket scene shown next to the next-topic recommendation.
def rocket_scene() -> str:
    return build_page(ROCKET_SCRIPT)
# Interactive 3D map of the LangGraph workflow, highlighting visited and current nodes.
def workflow_scene(visited: set[str], current: str | None) -> str:
    nodes = []
    for node_id, label, x, y, z in WORKFLOW_NODES:
        if node_id == current:
            node_state = "current"
        elif node_id in visited or (node_id == START_NODE and visited):
            node_state = "done"
        else:
            node_state = "todo"
        nodes.append({"id": node_id, "label": label, "x": x, "y": y, "z": z, "state": node_state})
    edges = [{"from": a, "to": b, "kind": kind} for a, b, kind in WORKFLOW_EDGES]
    script = WORKFLOW_SCRIPT.replace("__NODES__", json.dumps(nodes)).replace("__EDGES__", json.dumps(edges))
    return build_page(script, body=WORKFLOW_BODY, css=WORKFLOW_CSS)
