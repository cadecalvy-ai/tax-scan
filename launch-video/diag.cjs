// Locates what changed around given frames: node diag.cjs 819 827 ...
const http=require('http'),fs=require('fs'),path=require('path');const {chromium}=require('playwright-core');
const root=__dirname,types={'.html':'text/html','.js':'text/javascript','.jpg':'image/jpeg','.woff2':'font/woff2'};
const server=http.createServer((q,r)=>{const p=path.join(root,decodeURIComponent(q.url.split('?')[0].replace(/^\/+/,''))||'index.html');if(!fs.existsSync(p)||fs.statSync(p).isDirectory()){r.writeHead(404);return r.end();}r.writeHead(200,{'content-type':types[path.extname(p)]||'application/octet-stream'});fs.createReadStream(p).pipe(r);});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const b=await chromium.launch({channel:'chrome',headless:true});const pg=await b.newPage({viewport:{width:1440,height:1440}});
await pg.goto(`http://127.0.0.1:${server.address().port}/index.html?still=1`);await pg.evaluate(()=>window.ready);
for(const f of process.argv.slice(2).map(Number)){const r=await pg.evaluate(f=>{const c=document.getElementById('c'),x=c.getContext('2d');const grab=i=>{window.seek(i/60);return x.getImageData(0,0,1440,1440).data;};
 const fr=[f-2,f-1,f,f+1].map(grab);const out=[];
 for(let k=1;k<4;k++){const a=fr[k-1],d=fr[k];let n=0,x0=1e9,y0=1e9,x1=-1,y1=-1,mx=0;for(let y=0;y<1440;y+=2)for(let xx=0;xx<1440;xx+=2){const o=(y*1440+xx)*4,v=Math.abs(a[o]-d[o])+Math.abs(a[o+1]-d[o+1])+Math.abs(a[o+2]-d[o+2]);if(v>mx)mx=v;if(v>60){n++;if(xx<x0)x0=xx;if(xx>x1)x1=xx;if(y<y0)y0=y;if(y>y1)y1=y;}}
 out.push(`${f-2+k-1}->${f-2+k}: n=${n} max=${mx} bbox=[${x0},${y0}]-[${x1},${y1}]`);}return out;},f);console.log(`frame ${f} (t=${(f/60).toFixed(3)})\n  `+r.join('\n  '));}
await b.close();server.close();})();
