import adsk.core, adsk.fusion, math

def mm(v): return v/10.0
def P(x,y,z=0): return adsk.core.Point3D.create(mm(x),mm(y),mm(z))
def V(s): return adsk.core.ValueInput.createByString(s)
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
NEG = adsk.fusion.ExtentDirections.NegativeExtentDirection
POS = adsk.fusion.ExtentDirections.PositiveExtentDirection
T = 1.6  # kart kalinligi

def run(_ctx):
    app = adsk.core.Application.get()
    doc = None
    for i in range(app.documents.count):
        d = app.documents.item(i)
        if d.name == 'GridUp-PCB': doc = d
    if doc is None:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    doc.activate()
    des = adsk.fusion.Design.cast(app.activeProduct)
    comp = des.rootComponent
    for i in range(comp.bRepBodies.count-1, -1, -1):
        comp.bRepBodies.item(i).deleteMe()
    feats = comp.features; ext = feats.extrudeFeatures

    def plane(z):
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(comp.xYConstructionPlane, V('%g mm' % z))
        return comp.constructionPlanes.add(pi)
    def extr(sk, op, dist, direction=POS, symmetric=False, bodies=None):
        col = adsk.core.ObjectCollection.create()
        for i in range(sk.profiles.count): col.add(sk.profiles.item(i))
        inp = ext.createInput(col, op)
        if symmetric: inp.setSymmetricExtent(V('%g mm' % dist), False)
        else: inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(V('%g mm' % dist)), direction)
        if bodies: inp.participantBodies = bodies
        return ext.add(inp)
    def box(name, x1, y1, x2, y2, z0, h):
        sk = comp.sketches.add(plane(z0))
        sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P(x1,y1,z0)), sk.modelToSketchSpace(P(x2,y2,z0)))
        f = extr(sk, NEW, abs(h), POS if h > 0 else NEG)
        b = f.bodies.item(0); b.name = name; return b
    def cyl(name, cx, cy, d, z0, h):
        sk = comp.sketches.add(plane(z0))
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P(cx,cy,z0)), mm(d/2))
        f = extr(sk, NEW, abs(h), POS if h > 0 else NEG)
        b = f.bodies.item(0); b.name = name; return b

    # ---- KART 110 x 70 x 1.6, kose R2, M3 delikler (3.5,3.5), izolasyon yarigi x 81.5..82.5, Y 0..40
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P(0,0), P(110,70))
    pcb = extr(sk, NEW, T).bodies.item(0); pcb.name = 'PCB'
    col = adsk.core.ObjectCollection.create()
    for e in pcb.edges:
        g = e.geometry
        if isinstance(g, adsk.core.Line3D):
            dv = g.startPoint.vectorTo(g.endPoint)
            if abs(dv.x) < 1e-6 and abs(dv.y) < 1e-6: col.add(e)
    fi = feats.filletFeatures.createInput(); fi.addConstantRadiusEdgeSet(col, V('2 mm'), True); feats.filletFeatures.add(fi)
    sk = comp.sketches.add(comp.xYConstructionPlane)
    for (x,y) in [(7,7),(103,7),(7,63),(103,63)]:
        sk.sketchCurves.sketchCircles.addByCenterRadius(P(x,y), mm(1.6))
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P(81.5,-1), P(82.5,40))
    for (x,y) in [(0,0),(110,0),(0,70),(110,70)]:
        sk.sketchCurves.sketchCircles.addByCenterRadius(P(x,y), mm(4))   # kapak kose diregi boslugu
    extr(sk, CUT, 5, symmetric=True, bodies=[pcb])

    # ---- ON YUZ (Z = 1.6 ->)  [PCB koordinati = kutu - 5]
    cyl('MLX90640', 55, 37.5, 9.3, T, 6)           # TO-39, pencereye dayali
    box('SHT31', 7-1.25, 31-1.25, 7+1.25, 31+1.25, T, 0.9)
    cyl('LED', 25, 65, 3, T, 1.5)
    for i, x in enumerate([37.5, 37.5, 37.5]):
        pass
    box('R_pullup1', 37.5, 45.5, 39.5, 46.5, T, 0.6)
    box('R_pullup2', 37.5, 43.75, 39.5, 44.75, T, 0.6)
    box('C_100n', 37.5, 42, 38.75, 43, T, 0.6)
    box('EN_RC1', 29, 51.5, 31, 52.5, T, 0.6)
    box('EN_RC2', 29, 50, 31, 51, T, 0.6)
    box('Reset', 32, 49.75, 35, 52.75, T, 2)

    # ---- ARKA YUZ (Z = 0 <-)
    box('ESP32-S3-WROOM-1U', 10, 40.8, 28, 60, 0, -3.2)
    box('RAC05-05SK', 64, 42, 95.7, 68.7, 0, -21.8)          # datasheet 31,7 x 26,7 x 21,8 (THT); giris pinleri sag uc
    box('F1', 88, 22.25, 94.1, 25, 0, -2.6)
    box('MOV', 96.5, 21.5, 103.5, 25.5, 0, -8)
    box('Klemens 230V', 84, 0.5, 99.25, 8.5, 0, -10)   # L/N/PE 3 kutup 5,08 = 15,24
    box('LDO SOT-223', 70, 34, 76.5, 41, 0, -1.7)             # AP7361C-33E
    box('D1', 76.75, 39, 81, 41.65, 0, -1.5)
    box('D2', 76.75, 35, 81, 37.65, 0, -1.5)
    box('R_sarj', 60.5, 44.5, 62.5, 45.5, 0, -0.6)
    box('Bolucu1', 77.5, 29.5, 79.5, 30.5, 0, -0.6)
    box('Bolucu2', 77.5, 28, 79.5, 29, 0, -0.6)
    box('Boost U7', 55, 36, 57.5, 38, 0, -1)                   # TPS61099 WSON-6
    box('L_boost', 59, 35.5, 62, 38.5, 0, -1.5)               # 4,7 uH 3x3
    box('R_bal1', 52, 28, 54, 29, 0, -0.6)
    box('R_bal2', 52, 30.5, 54, 31.5, 0, -0.6)
    # superkap: 2x Eaton HV1030 (O10.5 x 31.5, 10 F 2,7 V) seri, yatik, eksen Y; merkezler x 61 / 72, y 17.75 (Y 2..33.5), govde Z 0..-10.5
    pi = comp.constructionPlanes.createInput(); pi.setByOffset(comp.xZConstructionPlane, V('17.75 mm'))
    pl = comp.constructionPlanes.add(pi)
    for i, cx in enumerate([61, 72]):
        sk = comp.sketches.add(pl)
        c = sk.modelToSketchSpace(P(cx, 17.75, -5.25))
        sk.sketchCurves.sketchCircles.addByCenterRadius(c, mm(5.25))
        f = extr(sk, NEW, 15.75, symmetric=True); sc = f.bodies.item(0); sc.name = 'Superkap%d' % (i+1)
        bb = sc.boundingBox
        print('superkap bbox', [round(v*10,2) for v in (bb.minPoint.x,bb.minPoint.y,bb.minPoint.z,bb.maxPoint.x,bb.maxPoint.y,bb.maxPoint.z)])
    box('MAX3485', 41.25, 14, 46.25, 20, 0, -1.5)
    box('R120', 47.5, 15, 48.5, 17, 0, -0.6)
    box('Klemens RS-485', 1, 11, 9, 26.25, 0, -10)
    for i, x in enumerate([25, 28, 31, 34]):
        box('R_burden%d' % (i+1), x, 14, x+2, 15, 0, -0.6)
    box('R_bias', 37, 13, 39, 15, 0, -0.6)
    box('Klemens CT', 25, 0.5, 53, 7.5, 0, -9)
    box('Genisleme 2x5', 11, 6.25, 24, 11.25, 0, -8.5)

    print('bodies:', comp.bRepBodies.count)
    bb = comp.boundingBox if hasattr(comp, 'boundingBox') else None
    zs = [comp.bRepBodies.item(i).boundingBox.minPoint.z*10 for i in range(comp.bRepBodies.count)]
    print('min Z (arka derinlik):', round(min(zs),2), 'max Z:', round(max(comp.bRepBodies.item(i).boundingBox.maxPoint.z*10 for i in range(comp.bRepBodies.count)),2))
    app.activeViewport.fit()
