# Spatial validation of the first real NISAR COG

**Later preparation follow-up:** The validated COG has now been registered as the existing first-scene backend reference, with its original historical job record backed up and the audit copy preserved. No second job was submitted; processing remains false. [Current second-scene readiness](harmony-second-test-readiness.md). Statements below about leaving the production record unpromoted describe the spatial-audit task itself.

**Verdict: VALID for technical spatial acceptance under the documented CRS-aware crop policy.** The old failure compared the geographic envelope of a UTM rectangle with the requested longitude/latitude rectangle. These are different geometries. The actual COG is consistent with native-grid window quantization and partial boundary pixels; the evidence does not indicate a wrong-area extraction.

This verdict does **not** establish mangrove disturbance, focusing/subswath quality, radiometric accuracy, absolute geolocation accuracy, tide comparability or scientific compatibility with another observation. Processing stays **false**. No new Harmony job or second-scene processing occurred.

Evidence: [full COG revalidation](harmony-spatial-validation.json), [independent geometric measurements](harmony-spatial-measurements.json), and the unchanged [historical first-test evidence](harmony-first-live-test.json).

## Data provenance and recovery

Existing NASA job: **`c9136c2d-e1ec-4669-b738-4a455f3b8f66`**, granule **G4405780437-ASF**, variable **frequencyA/HHHH**. The earlier INVALID-result cleanup had removed the local COG; the workspace search confirmed it was absent. To complete this audit, only that completed job's small COG was recovered through the existing authenticated backend, while processing remained disabled. No HDF5, replacement job or new acquisition was requested.

Recovery UTC window: **2026-11-15T07:31:15.168392Z – 2026-11-15T07:31:24.129301Z**. Size, CRS, dimensions and positive-pixel count match the previously recorded output. The original downloaded file had no retained hash, so byte-for-byte identity with that deleted copy is not claimed. The recovered copy's SHA-256 is:

```text
f9f232f2743c2839835d59726456a7d2eaa3bf7c04188d5a2d5d87cfd650df5d
```

Retained file: [first-real-cog.tif](../artifacts/harmony-spatial-audit/first-real-cog.tif), in the ignored audit directory. The full inspector rerun also verified source/variable identity using the actual output basename obtained by a read-only status lookup; no URI, signed parameters, cookie or credential was persisted. The historical job record was not promoted or overwritten, and scene two remains locked. This audit does not implicitly authorize further processing.

## Exact grid and geographic geometry

Requested WGS84 bounding box, **west/south/east/north**:

```text
[88.75, 21.85, 88.78, 21.88]
```

Returned grid: **EPSG:32645**, 313 columns × 334 rows, one float32 band, **10 m × 10 m**, NaN nodata. Exact projected bounds, in metres:

```text
[680810.0, 2417260.0, 683940.0, 2420600.0]
```

Affine coefficients `(a,b,c,d,e,f)`:

```text
(10.0, 0.0, 680810.0, 0.0, -10.0, 2420600.0)
Easting  = 680810 + 10 × column_edge
Northing = 2420600 - 10 × row_edge
```

Pixel centers use column/row **+0.5**, not the pixel edges. [Rasterio's affine documentation](https://rasterio.readthedocs.io/en/stable/topics/georeferencing.html) and [center/corner API](https://rasterio.readthedocs.io/en/stable/api/rasterio.transform.html) describe these conventions.

All PROJ transformations explicitly use **`always_xy=True`**, passing longitude before latitude even though the authoritative EPSG:4326 axis definition is latitude first. This follows [pyproj's axis-order guidance](https://pyproj4.github.io/pyproj/stable/api/transformer.html). The inverse-coordinate center check independently agrees with projected-AOI membership.

Actual outer pixel-edge corners, transformed to **longitude, latitude**:

| Corner | Longitude | Latitude |
| --- | --- | --- |
| NW | 88.75001738541567 | 21.880234889089312 |
| NE | 88.78030086029081 | 21.87991027280635 |
| SE | 88.77992687364363 | 21.84974895616848 |
| SW | 88.74964975241748 | 21.850073079995557 |

Their geographic envelope is **[88.74964975241748, 21.84974895616848, 88.78030086029081, 21.880234889089312]**. The north/south edges of this transformed footprint are not constant-latitude lines.

### Old discrepancy and tolerance

The previous rule used **0.00029378058664528893 degrees**, calculated as three times the larger geographic-envelope span per raster dimension. It treated that angular envelope difference as a source-grid alignment test.

| Edge | Absolute geographic-envelope difference, degrees | Approximate metres | Old rule |
| --- | --- | --- | --- |
| West | 0.0003502475825172269 | 36.20145 | Failed |
| South | 0.00025104383152196874 | 27.79764 | Passed |
| East | 0.00030086029080678145 | 31.09680 | Failed |
| North | 0.00023488908931312835 | 26.00895 | Passed |

Metres use WGS84 ellipsoidal geodesic distances along the AOI's middle latitude for longitude differences and middle longitude for latitude differences. They are approximate interpretations of envelope deltas, not measured registration errors.

## Diagnosis in the returned pixel grid

The densified requested AOI, transformed into EPSG:32645, has projected envelope:

```text
[680808.4994709694, 2417252.320098227,
 683947.2372494192, 2420609.5747688184]
```

In returned-grid pixel coordinates its envelope is **[-0.15005290305998642, -0.9574768818565644, 313.7237249419268, 334.76799017729354]**. The returned raster rectangle is `[0,0,313,334]` in that same frame.

| Grid side | Inward boundary difference, pixels | Metres on this 10 m grid |
| --- | --- | --- |
| Left | 0.15005290305998642 | 1.500529 |
| Top | 0.9574768818565644 | 9.574769 |
| Right | 0.7237249419267755 | 7.237249 |
| Bottom | 0.7679901772935409 | 7.679902 |

Every native envelope edge differs by **less than one pixel**, despite the misleading 31–36 m longitude-envelope differences. The returned affine is north-up and unrotated in UTM; its geographic footprint is tilted relative to the geographic AOI. There was no requested reprojection, and returned 10 m posting is consistent with the acquisition metadata. The HDF5 source grid and Harmony's internal rounding/resampling implementation were not inspected, so their exact implementation is not asserted.

There are **103,015** AOI-containing centers on the continued 10 m lattice. **102,933** occur in the returned raster; **82** missing centers are confined to its crop boundary. Their maximum depth inside the AOI is **0.441473996412775 pixel**, approximately **4.414740 m**. No deeper interior sample is missing. This is measured partial-edge loss, not complete continuous AOI coverage.

## Valid-data footprint and AOI intersection

Validity here means **finite, positive, GDAL-unmasked power**. It does not replace the GCOV focusing/subswath mask or a mangrove mask. The exact valid-cell footprint was polygonized independently from the real mask; it has one connected polygon. The production validator computes the same cell-union intersections without constructing a potentially huge polygon collection.

| Metric | Measured result |
| --- | --- |
| Raster pixels / masked pixels | 104,542 / 1,609 |
| Positive finite unmasked pixels | **102,933** |
| Positive centers inside AOI, projected check | **102,933** |
| Positive centers inside AOI, direct inverse lon/lat check | **102,933** |
| Positive centers outside AOI | **0** |
| Valid cells wholly disjoint from AOI | **0** |
| Available AOI center coverage by positive data | **100%** |
| Full-grid AOI center coverage, including missing edge samples | **99.92039994175606%** |
| Outer raster intersection / continuous AOI area | **99.91341981222554%** |
| Valid-cell intersection / continuous AOI area | **99.7909502777828%** |

Native projected areas, in square metres:

- AOI: **10,300,590.584708972**; outer raster: **10,454,200**.
- Exact valid-pixel-cell union: **10,293,300**.
- Valid-cell/AOI intersection: **10,279,057.228704907**.
- Valid-cell area outside the continuous AOI: **14,242.771295089688**, entirely associated with intersecting boundary cells. None of their positive centers is outside the AOI.

These are projected geometric areas, not forest-area estimates. Bounding boxes alone cannot reveal the masked corner regions or the difference between whole cells and centers.

The actual positive-center longitude/latitude envelope is **[88.75000007037816, 21.85000028633311, 88.77999992344213, 21.879999944578845]**, strictly inside the requested box.

Retained footprint artifacts: [native geometry with explicit CRS](../artifacts/harmony-spatial-audit/valid-data-footprint-native.json) and [WGS84 longitude/latitude GeoJSON](../artifacts/harmony-spatial-audit/valid-data-footprint-wgs84.geojson). Geographic display edges were densified to 10 m before transformation; metric acceptance calculations use native pixel cells.

## Implemented policy and explicit tolerances

The new `backend/app/spatial.py` is called by the existing `inspect_cog`; identity, COG format, CRS, dtype, transform, pixel and file-size checks remain in force. The former degree-envelope rule remains available as historical diagnostics but is no longer an acceptance gate.

1. Transform the requested longitude/latitude boundary with explicit XY order into the returned raster's pixel frame. Double boundary sampling until the polygon's Hausdorff change is **≤0.000001 pixel**; reject nonconvergence, nonfinite or invalid geometry. This file converged at **256 segments/edge**, change **4.6202429107942517e-7 pixel**.
2. Permit at most **one native raster pixel** of inward or outward window-edge quantization on each side, plus the numerical epsilon above. This is a pixel-window rounding bound, not a geographic registration tolerance. [Rasterio window geometry](https://rasterio.readthedocs.io/en/stable/api/rasterio.features.html) documents the relationship between geometry bounds and integer window offsets/sizes. This policy does not claim NASA uses that exact helper.
3. Examine continued-lattice centers omitted by the returned window. Reject any missing AOI center more than **half a pixel** inside its boundary. Half a pixel is the center-to-edge sampling scale; it is not an adjustable completeness percentage. Record all boundary omissions. Reject AOIs too small to make this test meaningful.
4. Require positive valid centers in the AOI. Treat each valid datum as its closed pixel cell and reject any valid cell wholly disjoint from the AOI, apart from the **1e-6-pixel numerical epsilon**. An intersecting edge cell can have a center just outside the polygon under an all-touched convention; it is reported separately. This real COG has no such outside centers.
5. Report center completeness and exact cell-union intersection areas. Interior nodata gaps are surfaced, not reclassified as valid or hidden by a bounding envelope. No new ecological completeness threshold was invented.

The one-cell/half-cell limits derive from integer-window and pixel-center geometry. They are independent of the measured geographic-envelope errors and are not increased until the file passes. Outputs displaced or clipped beyond those limits, oversized full-scene outputs, wrong-coordinate outputs, empty power layers and disjoint valid data are rejected. Absolute geolocation accuracy and subtle within-pixel misregistration still need independent reference data.

## Rerun, preservation and tests

The full existing COG inspector returned **verified=true** on the recovered real file with the new policy: COG/GTiff/tiled structure, source/variable identity, EPSG:32645, one float32 band, valid affine, NaN mask, positive pixels and spatial validation all passed. The cache hash was checked again before revalidation.

Latest offline rerun UTC: **2026-11-15T07:47:37.069920Z – 2026-11-15T07:47:37.215894Z**. It used the retained output-identity record and made no network request. Reproduce without processing or downloads:

```powershell
.venv\Scripts\python.exe -m scripts.measure_spatial_audit
.venv\Scripts\python.exe -m scripts.validate_cached_spatial
```

`pyproj` was added explicitly and pinned to the installed **3.8.0** in the backend lock. Installed dependencies pass compatibility checking. Authentication, AOIs, source granules, job architecture and existing tests were preserved.

- Backend: **144 passed, 1 opt-in metadata test skipped**, **6.68 seconds**, existing Starlette/httpx warning only.
- Frontend: **9 passed**, two files.
- Thirteen new synthetic cases cover projected window padding and inward snapping, partial edge cells, wrong CRS/coordinate units, displaced location, missing CRS, empty/zero layers, disjoint positive cells, one-pixel tolerance boundaries, excessive cropping/oversized output and axis-order mistakes. Existing tests remain passing.
- The original test JSON and production provenance remain historical. No automatic job-state promotion or scene-two unlock was performed. The diagnostic COG is retained in the ignored audit directory for review; no raster is committed.
- A fresh settings check confirms **`HARMONY_PROCESSING_ENABLED=false`**. There was **zero new processing**, no raw HDF5, no second-scene access and no credential/signed-URL exposure.

**Final verdict: VALID for this COG's technical spatial validation.** This resolves the earlier extent-rule false rejection without establishing mangrove disturbance or scientific compatibility with the second observation.
