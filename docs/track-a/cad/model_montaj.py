# Fusion 360 — GridUp-Kutu + GridUp-PCB montaji. Bos bir tasarim belgesinde calistir (bulutta iki belge kayitli olmali).
# PCB kutu icinde (5, 5, 39.4) mm: on yuzu Z = 41, MLX90640 tepesi Z = 47 (IR pencere plakasina dayali).
import adsk.core, adsk.fusion

def run(_ctx):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    folder = None
    hub = app.data.activeHub
    for i in range(hub.dataProjects.count):
        p = hub.dataProjects.item(i)
        if p.name == 'Default Project': folder = p.rootFolder
    files = {}
    for i in range(folder.dataFiles.count):
        f = folder.dataFiles.item(i)
        if f.fileExtension == 'f3d': files[f.name] = f
    have = [root.occurrences.item(i).component.name for i in range(root.occurrences.count)]
    if 'GridUp-Kutu' not in have:
        root.occurrences.addByInsert(files['GridUp-Kutu'], adsk.core.Matrix3D.create(), True)
    if 'GridUp-PCB' not in have:
        m = adsk.core.Matrix3D.create(); m.translation = adsk.core.Vector3D.create(0.5, 0.5, 3.94)
        root.occurrences.addByInsert(files['GridUp-PCB'], m, True)
    for i in range(root.occurrences.count):
        o = root.occurrences.item(i); bb = o.bRepBodies.item(0).boundingBox
        print(o.component.name, [round(v*10, 2) for v in (bb.minPoint.x, bb.minPoint.y, bb.minPoint.z, bb.maxPoint.x, bb.maxPoint.y, bb.maxPoint.z)])
    app.activeViewport.fit()
