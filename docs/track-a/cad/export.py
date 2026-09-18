# Fusion 360 — acik GridUp-* belgelerini .f3d (+ .step) olarak OUT klasorune aktarir.
import adsk.core, adsk.fusion, os
OUT = globals().get('EXPORT_DIR', os.path.dirname(os.path.abspath(__file__)))

def run(_ctx):
    app = adsk.core.Application.get()
    done = set()
    for i in range(app.documents.count):
        d = app.documents.item(i)
        if d.objectType != 'adsk::fusion::FusionDocument' or not d.name.startswith('GridUp-') or d.name in done: continue
        done.add(d.name); d.activate()
        em = adsk.fusion.Design.cast(d.products.itemByProductType('DesignProductType')).exportManager
        em.execute(em.createFusionArchiveExportOptions(os.path.join(OUT, d.name + '.f3d')))
        em.execute(em.createSTEPExportOptions(os.path.join(OUT, d.name + '.step')))
        print('exported', d.name)
