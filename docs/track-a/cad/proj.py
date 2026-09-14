# Fusion 360 icinde calisir (Fusion MCP 'script' veya Scripts menusu). Aktif tasarimdan ortografik projeksiyon:
# kenarlar + silindir siluetleri, findBRepUsingRay ile gizli cizgi ayiklama, istege bagli klip + kesit (planeIntersection).
# CFG: JSON {out, views:[{name, d, u, include?, exclude?, include_prefix?, exclude_prefix?, clip?{axis,min|max}, section?}]}
# Kullanim: globals()['CFG_PATH'] = '.../cfg_kutu.json' verip bu dosyayi exec et; run(None) cagir. Cikti JSON: mm, y asagi.
import adsk.core, adsk.fusion, math, json, time

import os
CFG = globals().get('CFG_PATH')

def norm(v):
    l = math.sqrt(v[0]**2+v[1]**2+v[2]**2); return (v[0]/l, v[1]/l, v[2]/l)
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a,b): return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]
def sub(a,b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def add(a,b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def mul(a,s): return (a[0]*s, a[1]*s, a[2]*s)
def dist3(a,b): return math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2)

def all_bodies(comp):
    # kok govdeler + alt occurrence govdeleri (montaj baglaminda proxy)
    out = [(comp.bRepBodies.item(i), '') for i in range(comp.bRepBodies.count)]
    for j in range(comp.allOccurrences.count):
        occ = comp.allOccurrences.item(j)
        for i in range(occ.bRepBodies.count):
            out.append((occ.bRepBodies.item(i), occ.component.name + '/'))
    return out

def run(_ctx):
    cfg = json.load(open(CFG))
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    comp = des.rootComponent
    t0 = time.time()
    bodies = [(b, pre) for (b, pre) in all_bodies(comp) if b.isVisible]
    names = {b.entityToken: pre + b.name for b, pre in bodies}
    result = {}
    for view in cfg['views']:
        d = norm(tuple(view['d'])); u = tuple(view['u'])
        up = norm(sub(u, mul(d, dot(u, d)))); r = cross(d, up)
        inc = view.get('include'); exc = set(view.get('exclude', []))
        incp = view.get('include_prefix'); excp = view.get('exclude_prefix', [])
        def selok(n):
            if inc is not None and n not in inc: return False
            if n in exc: return False
            if incp is not None and not any(n.startswith(p) for p in incp): return False
            if any(n.startswith(p) for p in excp): return False
            return True
        sel = [(b, pre) for (b, pre) in bodies if selok(pre + b.name)]
        seltok = {b.entityToken for b, _ in sel}
        dvec = adsk.core.Vector3D.create(*d)
        clip = view.get('clip')  # {'axis':0..2, 'max': mm} veya {'axis', 'min': mm}
        cmax = clip['max']/10.0 if clip and 'max' in clip else 1e9
        cmin = clip['min']/10.0 if clip and 'min' in clip else -1e9
        def keep(p): return (clip is None) or (cmin - 1e-4 <= p[clip['axis']] <= cmax + 1e-4)
        def proj(p): return (round(dot(p, r)*10, 3), round(-dot(p, up)*10, 3))
        def visible(p):
            origin = adsk.core.Point3D.create(*sub(p, mul(d, 100.0)))
            hits = adsk.core.ObjectCollection.create()
            ents = comp.findBRepUsingRay(origin, dvec, adsk.fusion.BRepEntityTypes.BRepFaceEntityType, -1.0, False, hits)
            dmin = 1e9
            for i in range(hits.count):
                f = ents.item(i)
                if f.body.entityToken not in seltok: continue
                hp = hits.item(i)
                if not keep((hp.x, hp.y, hp.z)): continue
                dist = origin.distanceTo(hp)
                if dist < dmin: dmin = dist
            return dmin >= 100.0 - 0.003
        polys = []
        for b, pre in sel:
            bname = pre + b.name
            for e in b.edges:
                faces = [e.faces.item(i) for i in range(e.faces.count)]
                ev = e.evaluator
                ok, pmin, pmax = ev.getParameterExtents()
                ok, pts = ev.getStrokes(pmin, pmax, 0.002)
                Pp = [(p.x, p.y, p.z) for p in pts if keep((p.x, p.y, p.z))]
                if len(Pp) < 2: continue
                if not view.get('all_edges'):
                    mid = Pp[len(Pp)//2]; mp = adsk.core.Point3D.create(*mid)
                    front = False
                    for f in faces:
                        ok, n = f.evaluator.getNormalAtPoint(mp)
                        if ok and dot((n.x, n.y, n.z), d) < 1e-6: front = True; break
                    if not front: continue
                cur = [Pp[0]]; curvis = None
                def flush(cur, vis):
                    if len(cur) >= 2 and vis: polys.append(dict(body=bname, kind='edge', pts=[proj(q) for q in cur]))
                for i in range(1, len(Pp)):
                    vis = visible(mul(add(Pp[i-1], Pp[i]), 0.5))
                    if curvis is None: curvis = vis
                    if vis != curvis:
                        flush(cur, curvis); cur = [Pp[i-1]]; curvis = vis
                    cur.append(Pp[i])
                flush(cur, curvis)
            for f in b.faces:
                g = f.geometry
                if not isinstance(g, adsk.core.Cylinder): continue
                a = norm((g.axis.x, g.axis.y, g.axis.z))
                if abs(dot(a, d)) > 0.999: continue
                s = norm(cross(a, d)); o = (g.origin.x, g.origin.y, g.origin.z)
                ts = []
                for e in f.edges:
                    for v in (e.startVertex, e.endVertex):
                        q = (v.geometry.x, v.geometry.y, v.geometry.z); ts.append(dot(sub(q, o), a))
                if not ts: continue
                tmin, tmax = min(ts), max(ts)
                if tmax - tmin < 1e-4: continue
                for sign in (1, -1):
                    base = add(o, mul(s, sign*g.radius))
                    p0 = add(base, mul(a, tmin)); p1 = add(base, mul(a, tmax))
                    midp = adsk.core.Point3D.create(*mul(add(p0, p1), 0.5))
                    ok, prm = f.evaluator.getParameterAtPoint(midp)
                    if not ok or not f.evaluator.isParameterOnFace(prm): continue
                    if visible(add(mul(add(p0, p1), 0.5), mul(s, sign*0.001))):
                        polys.append(dict(body=bname, kind='sil', pts=[proj(p0), proj(p1)]))
        if clip and view.get('section'):
            tmp = adsk.fusion.TemporaryBRepManager.get()
            nrm = [0,0,0]; nrm[clip['axis']] = 1
            org = [0,0,0]; org[clip['axis']] = cmax if 'max' in clip else cmin
            plane = adsk.core.Plane.create(adsk.core.Point3D.create(*org), adsk.core.Vector3D.create(*nrm))
            for b, pre in sel:
                try:
                    wb = tmp.planeIntersection(tmp.copy(b), plane)
                except Exception:
                    continue   # duzlemi kesmiyor
                if wb is None: continue
                segs = []
                for e in wb.edges:
                    ev = e.evaluator
                    ok, pmin, pmax = ev.getParameterExtents()
                    ok, pts = ev.getStrokes(pmin, pmax, 0.002)
                    segs.append([(p.x, p.y, p.z) for p in pts])
                # zincirle
                loops = []
                while segs:
                    cur = segs.pop(0)
                    changed = True
                    while changed:
                        changed = False
                        for k, sg in enumerate(segs):
                            if dist3(cur[-1], sg[0]) < 1e-3: cur += sg[1:]; segs.pop(k); changed = True; break
                            if dist3(cur[-1], sg[-1]) < 1e-3: cur += sg[-2::-1]; segs.pop(k); changed = True; break
                            if dist3(cur[0], sg[-1]) < 1e-3: cur = sg[:-1] + cur; segs.pop(k); changed = True; break
                            if dist3(cur[0], sg[0]) < 1e-3: cur = sg[::-1][:-1] + cur; segs.pop(k); changed = True; break
                    loops.append(cur)
                for lp in loops:
                    polys.append(dict(body=pre + b.name, kind='cut', pts=[proj(q) for q in lp]))
        result[view['name']] = polys
        print(view['name'], 'polys', len(polys), 't=%.1f' % (time.time()-t0))
    out = cfg['out'] if os.path.isabs(cfg['out']) else os.path.join(os.path.dirname(os.path.abspath(CFG)), cfg['out'])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w') as fh: json.dump(result, fh)
    print('written', out)
