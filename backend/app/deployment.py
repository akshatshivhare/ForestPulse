"""Small, offline checks for the assets required by the public demonstration."""
from . import image_data

DEMO_IDS = ('sim-rgb-before', 'sim-rgb-after', 'sim-sar-before', 'sim-sar-after')


def validate_demo_assets():
    records = {entry['id']: entry for entry in image_data.entries()}
    total = 0
    for image_id in DEMO_IDS:
        entry = records.get(image_id)
        if not entry or entry['is_simulated'] is not True or entry.get('acquisition_date') is not None:
            raise RuntimeError('Required explicitly simulated gallery metadata is missing or mislabeled.')
        path = image_data.asset_path(entry)
        raster = image_data.load(entry)
        if not raster['valid'].any():
            raise RuntimeError('A required gallery sample contains no valid pixels.')
        total += path.stat().st_size
    return {'required_demo_images': len(DEMO_IDS), 'source_bytes': total}
