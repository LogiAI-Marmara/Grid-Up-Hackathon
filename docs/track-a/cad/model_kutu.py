# Fusion 360 — modul kutusu 120 x 80 x 50 (04-mekanik-yerlesim.md). Bos bir Parca Tasarimi belgesinde calistir.
# Koordinat: X sag, Y yukari, Z on yuz normali (kapak +Z). mm degerleri; API ic birimi cm.
import adsk.core, adsk.fusion, math

def mm(v): return v/10.0
def P(x,y,z=0): return adsk.core.Point3D.create(mm(x),mm(y),mm(z))
def V(s): return adsk.core.ValueInput.createByString(s)
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
NEG = adsk.fusion.ExtentDirections.NegativeExtentDirection
POS = adsk.fusion.ExtentDirections.PositiveExtentDirection

KAPAK_VIDA = [(5,5),(115,5),(5,75),(115,75)]        # M3, kose direkleri O7
PCB_DIKME = [(12,12),(108,12),(12,68),(108,68)]      # O6, M3 — PCB (7,7) vb. ile hizali (PCB = kutu - 5)

def run(_ctx):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    comp = des.rootComponent
    # temiz baslangic: eski zincir timeline'da kalirsa her calistirma 'Govde15', 'Kapak (1)' gibi kopya govde uretir
    tl = des.timeline
    if tl.count: tl.markerPosition = 0; tl.deleteAllAfterMarker()
    for i in range(comp.bRepBodies.count-1, -1, -1): comp.bRepBodies.item(i).deleteMe()
    feats = comp.features; ext = feats.extrudeFeatures

    def plane(z):
        pi = comp.constructionPlanes.createInput(); pi.setByOffset(comp.xYConstructionPlane, V('%g mm' % z))
        return comp.constructionPlanes.add(pi)
    def sketch_on(pl): return comp.sketches.add(pl)
    def circ(sk, x, y, z, d): sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P(x,y,z)), mm(d/2))
    def rect(sk, x1,y1,x2,y2, z=0): sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P(x1,y1,z)), sk.modelToSketchSpace(P(x2,y2,z)))
    def slot(sk, cx, cy, length, width, z=0):
        r = width/2; x1 = cx-length/2+r; x2 = cx+length/2-r
        L = sk.sketchCurves.sketchLines; A = sk.sketchCurves.sketchArcs
        m = lambda x,y: sk.modelToSketchSpace(P(x,y,z))
        L.addByTwoPoints(m(x1,cy-r), m(x2,cy-r)); A.addByCenterStartSweep(m(x2,cy), m(x2,cy-r), math.pi)
        L.addByTwoPoints(m(x2,cy+r), m(x1,cy+r)); A.addByCenterStartSweep(m(x1,cy), m(x1,cy+r), math.pi)
    def extr(sk, op, dist, direction=None, symmetric=False, bodies=None):
        col = adsk.core.ObjectCollection.create()
        for i in range(sk.profiles.count): col.add(sk.profiles.item(i))
        inp = ext.createInput(col, op)
        if symmetric: inp.setSymmetricExtent(V('%g mm' % dist), False)
        else: inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(V('%g mm' % dist)), direction or POS)
        if bodies: inp.participantBodies = bodies
        return ext.add(inp)
    def fillet_vertical(body, r, length):
        col = adsk.core.ObjectCollection.create()
        for e in body.edges:
            g = e.geometry
            if isinstance(g, adsk.core.Line3D):
                d = g.startPoint.vectorTo(g.endPoint)
                if abs(d.x) < 1e-6 and abs(d.y) < 1e-6 and abs(e.length - mm(length)) < 1e-4: col.add(e)
        fi = feats.filletFeatures.createInput(); fi.addConstantRadiusEdgeSet(col, V('%g mm' % r), True); feats.filletFeatures.add(fi)

    # GOVDE 120 x 80, Z 0..46, duvar 2, kose R4, on acik
    sk = sketch_on(comp.xYConstructionPlane); rect(sk, 0,0,120,80)
    govde = extr(sk, NEW, 46).bodies.item(0); govde.name = 'G' + chr(246) + 'vde'
    fillet_vertical(govde, 4, 46)
    top = None
    for fc in govde.faces:
        if isinstance(fc.geometry, adsk.core.Plane) and abs(fc.boundingBox.minPoint.z - mm(46)) < 1e-4 and abs(fc.boundingBox.maxPoint.z - mm(46)) < 1e-4: top = fc
    fcol = adsk.core.ObjectCollection.create(); fcol.add(top)
    si = feats.shellFeatures.createInput(fcol, False); si.insideThickness = V('2 mm'); feats.shellFeatures.add(si)
    # kapak vida direkleri O7, Z 0..46
    sk = sketch_on(comp.xYConstructionPlane)
    for (x,y) in KAPAK_VIDA: circ(sk, x,y,0, 7)
    extr(sk, JOIN, 46, bodies=[govde])
    # PCB dikmeleri O6, Z 0..39.4 + M3 (O2.5) delik 8 mm
    sk = sketch_on(comp.xYConstructionPlane)
    for (x,y) in PCB_DIKME: circ(sk, x,y,0, 6)
    extr(sk, JOIN, 39.4, bodies=[govde])
    sk = sketch_on(plane(39.4))
    for (x,y) in PCB_DIKME: circ(sk, x,y,39.4, 2.5)
    extr(sk, CUT, 8, NEG, bodies=[govde])

    # KAPAK Z 46..50
    sk = sketch_on(plane(46)); rect(sk, 0,0,120,80, 46)
    kapak = extr(sk, NEW, 4, POS).bodies.item(0); kapak.name = 'Kapak'
    fillet_vertical(kapak, 4, 4)
    pl50 = plane(50)
    sk = sketch_on(pl50); circ(sk, 60,42.5,50, 23); extr(sk, JOIN, 2, POS, bodies=[kapak])          # IR yuva O23 +2
    sk = sketch_on(pl50); circ(sk, 60,42.5,50, 15); extr(sk, CUT, 8, symmetric=True, bodies=[kapak])  # IR pencere O15
    ecol = adsk.core.ObjectCollection.create()
    for e in kapak.edges:
        g = e.geometry
        if isinstance(g, adsk.core.Circle3D) and abs(g.radius - mm(7.5)) < 1e-4 and abs(g.center.z - mm(52)) < 1e-4: ecol.add(e)
    ci = feats.chamferFeatures.createInput(ecol, False); ci.setToEqualDistance(V('3 mm')); feats.chamferFeatures.add(ci)  # konik pah
    sk = sketch_on(pl50); circ(sk, 12,36,50, 9); extr(sk, JOIN, 1.5, POS, bodies=[kapak])            # vent halkasi
    sk = sketch_on(pl50); circ(sk, 12,36,50, 6.5); extr(sk, CUT, 8, symmetric=True, bodies=[kapak])   # vent M6
    sk = sketch_on(pl50); circ(sk, 30,70,50, 3.2); extr(sk, CUT, 8, symmetric=True, bodies=[kapak])   # LED
    sk = sketch_on(pl50)
    for (x,y) in KAPAK_VIDA: circ(sk, x,y,50, 3.2)
    extr(sk, CUT, 8, symmetric=True, bodies=[kapak])
    sk = sketch_on(pl50)
    for (x,y) in KAPAK_VIDA: circ(sk, x,y,50, 2.5)
    extr(sk, CUT, 16, NEG, bodies=[govde])

    # IR pencere plakasi O15 x 1 (Z 47..48)
    sk = sketch_on(plane(47.5)); circ(sk, 60,42.5,47.5, 15)
    extr(sk, NEW, 0.5, symmetric=True).bodies.item(0).name = 'IR pencere'

    # ALT YUZ (Y=0), merkez Z=23, soldan saga = PCB klemens sirasi: RS-485 PG7 O12.5 / SMA O6.4 / CT PG7 O12.5 / 230 V PG7 O12.5
    sk = sketch_on(comp.xZConstructionPlane)
    for (x,d) in [(17.5,12.5),(40,6.4),(65,12.5),(102.5,12.5)]:
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P(x,0,23)), mm(d/2))
    extr(sk, CUT, 3, symmetric=True, bodies=[govde])

    # ARKA YUZ (Z=0): oval yuva M5 15 x 5.5, miknatis cepleri O7 x 1, DIN klips 35 x 42 x 5
    sk = sketch_on(comp.xYConstructionPlane); slot(sk, 17.5, 45.25, 15, 5.5); slot(sk, 102.5, 45.25, 15, 5.5)
    extr(sk, CUT, 3, symmetric=True, bodies=[govde])
    sk = sketch_on(comp.xYConstructionPlane)
    for (x,y) in [(7.5,7.5),(112.5,7.5),(7.5,72.5),(112.5,72.5)]: circ(sk, x,y,0, 7)
    extr(sk, CUT, 1, symmetric=True, bodies=[govde])
    sk = sketch_on(comp.xYConstructionPlane); rect(sk, 42.5,20,77.5,62)
    din = extr(sk, NEW, 5, NEG).bodies.item(0); din.name = 'DIN klips'
    sk = sketch_on(plane(-5)); rect(sk, 42.5,23.25,77.5,58.75,-5)
    extr(sk, CUT, 3, symmetric=True, bodies=[din])
    print('bodies:', [comp.bRepBodies.item(i).name.encode('ascii','replace').decode() for i in range(comp.bRepBodies.count)])
    app.activeViewport.fit()
