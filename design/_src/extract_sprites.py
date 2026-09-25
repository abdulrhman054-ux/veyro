import re,json
t=open(r'D:/Veyro/design/_src/council/template.html',encoding='utf-8').read()
lines=t.split('\n')
names=['Ollie','Pip','Buzz','Benny','Bolt','Bruno','Tank','Leo']
out={}
idx=[i for i,l in enumerate(lines) if 'class="fr down"' in l]
for n,i in zip(names,idx):
    l=lines[i]
    frames={}
    for m in re.finditer(r'<svg class="fr (\w+)"[^>]*>(.*?)</svg>',l):
        rects=[(int(a),int(b),int(c),int(d),e) for a,b,c,d,e in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" fill="(#[0-9A-Fa-f]+)"',m.group(2))]
        other=re.sub(r'<rect[^>]*></rect>','',m.group(2))
        frames[m.group(1)]={'rects':rects,'other':other}
    lid=re.findall(r'class="lid"',l)
    out[n]=frames
    print(n,{k:(len(v['rects']),v['other'][:300]) for k,v in frames.items()})
json.dump(out,open(r'D:/Veyro/design/extracted/sprites_raw.json','w'))
# preview
html=['<html><body style="background:#F2E2C0;display:flex;flex-wrap:wrap;gap:20px">']
for n,fr in out.items():
    for k,v in fr.items():
        r=''.join(f'<rect x="{a}" y="{b}" width="{c}" height="{d}" fill="{e}"/>' for a,b,c,d,e in v['rects'])
        html.append(f'<div><svg width="147" height="161" viewBox="-0.5 -0.5 21 23" shape-rendering="crispEdges">{r}{v["other"]}</svg><div>{n} {k}</div></div>')
open(r'D:/Veyro/design/extracted/sprites_preview.html','w').write(''.join(html))
