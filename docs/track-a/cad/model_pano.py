import adsk.core, adsk.fusion, math

def mm(v): return v/10.0
def P(x,y,z=0): return adsk.core.Point3D.create(mm(x),mm(y),mm(z))
def V(s): return adsk.core.ValueInput.createByString(s)
NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
NEG = adsk.fusion.ExtentDirections.NegativeExtentDirection
POS = adsk.fusion.ExtentDirections.PositiveExtentDirection

def run(_ctx):
    app = adsk.core.Application.get()
    doc = None
    for i in range(app.documents.count):
        d = app.documents.item(i)
        if d.name.split(' (')[0] == 'GridUp-Pano': doc = d   # '(~recovered)' ekini tolere et
    if doc is None:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    doc.activate()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    for i in range(root.bRepBodies.count-1, -1, -1): root.bRepBodies.item(i).deleteMe()
    for i in range(root.occurrences.count-1, -1, -1): root.occurrences.item(i).deleteMe()
    comp = root
    feats = comp.features; ext = feats.extrudeFeatures

    def plane(z):
        pi = comp.constructionPlanes.createInput()
        pi.setByOffset(comp.xYConstructionPlane, V('%g mm' % z))
        return comp.constructionPlanes.add(pi)
    def extr(sk, op, dist, direction=POS, bodies=None):
        col = adsk.core.ObjectCollection.create()
        for i in range(sk.profiles.count): col.add(sk.profiles.item(i))
        inp = ext.createInput(col, op)
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(V('%g mm' % dist)), direction)
        if bodies: inp.participantBodies = bodies
        return ext.add(inp)
    def box(name, x1, y1, x2, y2, z0, h, op=NEW, bodies=None):
        sk = comp.sketches.add(plane(z0))
        sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P(x1,y1,z0)), sk.modelToSketchSpace(P(x2,y2,z0)))
        f = extr(sk, op, abs(h), POS if h > 0 else NEG, bodies)
        if op == NEW:
            b = f.bodies.item(0); b.name = name; return b
        return f

    # GOVDE: dis 1600 x 1500 x 450, Z -450..0, on acik, sac 2 mm; arka montaj plakasi 20 mm
    sk = comp.sketches.add(plane(-450))
    sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P(0,0,-450)), sk.modelToSketchSpace(P(1600,1500,-450)))
    govde = extr(sk, NEW, 450, POS).bodies.item(0); govde.name = 'Pano govde'
    top = None
    for fc in govde.faces:
        if isinstance(fc.geometry, adsk.core.Plane) and abs(fc.boundingBox.minPoint.z) < 1e-4 and abs(fc.boundingBox.maxPoint.z) < 1e-4: top = fc
    fcol = adsk.core.ObjectCollection.create(); fcol.add(top)
    si = feats.shellFeatures.createInput(fcol, False); si.insideThickness = V('2 mm'); feats.shellFeatures.add(si)
    box('plaka', 2, 2, 1598, 1498, -448, -0.0001 + 18, JOIN, [govde]) if False else None
    sk = comp.sketches.add(plane(-448))
    sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P(2,2,-448)), sk.modelToSketchSpace(P(1598,1498,-448)))
    pf = extr(sk, JOIN, 18, POS, [govde])   # montaj plakasi on yuzu Z = -430
    plaka = [pf.bodies.item(i) for i in range(pf.bodies.count) if pf.bodies.item(i) != govde]
    for b in plaka: b.name = 'Pano plaka'     # JOIN govdeye birlesmezse ayri govde: adlandir, cep kesimine dahil et

    # KAPAK (kapali konum) Z 0..22
    box('Kapak', 0, 0, 1600, 1500, 0, 22)

    # CIHAZLAR (arka plaka on yuzu Z = -430'dan one)
    Z0 = -430
    box('Sabit kompanzasyon', 90, 1050, 240, 1200, Z0, 50)
    box('Modem', 1290, 1050, 1490, 1140, Z0, 50)
    box('T1 olcu (analizor)', 1320, 790, 1530, 940, Z0, 50)
    box('Kontrol', 1320, 630, 1530, 740, Z0, 50)
    # BARA SISTEMI: 3 yatay bara (L1/L2/L3), 185 mm adim (sartname Tablo 8 DSYA). Kesit 1600 kVA icin 2x(100x10) mm2
    #   (sartname EK-I/8 Tablo 8); burada faz basina TEK 100x10 bara modellendi — ikinci bara (toplam 20 mm)
    #   s=0 kabulune sigmaz, karar bekliyor. Mesnet izolatorleri arkada.
    # Bara standoff'u (s) kaynaksiz -> s = 0 en iyimser kabul: bara on yuzu = plaka on yuzu (Z0).
    # Plaka NH bolgesinde cep (Z -448..-430), bara + izolator bu cebin icinde (sematik).
    box('Plaka cebi', 30, 500, 1270, 990, -448, 18, CUT, [govde] + plaka)
    for i, yc in enumerate([930, 745, 560]):
        box('Bara L%d' % (i+1), 40, yc - 50, 1260, yc + 50, Z0 - 10, 10)
        for j, xc in enumerate([70, 650, 1230]):
            box('Mesnet izolatoru L%d-%d' % (i+1, j+1), xc - 20, yc - 55, xc + 20, yc + 55, -448, 8)
    # NH dikey yuk ayirici: derinlik 141,5 mm bara on yuzunden (Eaton EBV 00, Pub. 10275 s.5)
    for r, (y1, y2) in enumerate([(820, 940), (685, 805), (550, 670)]):
        for k in range(12):
            x1 = 50 + k*100 + 8
            box('NH s%d-%02d' % (r+1, k+1), x1, y1, x1 + 84, y2, Z0, 141.5)
    box('Klemens sirasi', 50, 440, 1250, 495, Z0, 45)

    # MODUL: GridUp-Kutu, kapak ic yuzune (Z=0), 180 deg Y ekseni etrafinda; merkez (650, 690)
    hub = app.data.activeHub
    folder = None
    for i in range(hub.dataProjects.count):
        p = hub.dataProjects.item(i)
        if p.name == 'Default Project': folder = p.rootFolder
    kutu = None
    for i in range(folder.dataFiles.count):
        f = folder.dataFiles.item(i)
        if f.name == 'GridUp-Kutu-Montaj': kutu = f
    m = adsk.core.Matrix3D.create()
    m.setToRotation(math.pi, adsk.core.Vector3D.create(0,1,0), adsk.core.Point3D.create(0,0,0))
    m.translation = adsk.core.Vector3D.create(mm(710), mm(650), mm(-5))
    occ = root.occurrences.addByInsert(kutu, m, True)
    print('modul occ:', occ.component.name, 'bodies', occ.bRepBodies.count)
    for j in range(occ.bRepBodies.count):
        b = occ.bRepBodies.item(j)
        if 'vde' in b.name or b.name == 'Kapak':
            bb = b.boundingBox
            print('  ', b.name, [round(v*10,1) for v in (bb.minPoint.x,bb.minPoint.y,bb.minPoint.z,bb.maxPoint.x,bb.maxPoint.y,bb.maxPoint.z)])
    for j in range(occ.childOccurrences.count):
        o2 = occ.childOccurrences.item(j)
        for k in range(o2.bRepBodies.count):
            b = o2.bRepBodies.item(k)
            if b.name.startswith('MLX') or 'vde' in b.name or b.name == 'IR pencere':
                bb = b.boundingBox
                print('  ', o2.component.name, b.name, [round(v*10,1) for v in (bb.minPoint.x,bb.minPoint.y,bb.minPoint.z,bb.maxPoint.x,bb.maxPoint.y,bb.maxPoint.z)])
    print('root bodies', root.bRepBodies.count)
    app.activeViewport.fit()
