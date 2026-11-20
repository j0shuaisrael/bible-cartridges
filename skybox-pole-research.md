# Skybox pole research — why the zenith warps and what others do about it

Date: 2026-11-19. Background research only — no viewer files were changed.
Model: "FREE - SkyBox Anime Sky" by Paul (Sketchfab, CC-BY),
https://sketchfab.com/3d-models/free-skybox-anime-sky-56a60c1d1e8b44eabff138374f996d8f
Viewer: three.js r160, plain static page; the sky is the GLB's UV sphere
(2,143 verts, 3,968 tris) with its 4096×2048 equirectangular panorama,
rendered unlit (MeshBasicMaterial, white base, DoubleSide, toneMapped false).
The texture is decoded by hand from the GLB's BIN chunk at runtime.

## 1. The problem, as measured in our own files

Three separate effects stack at the zenith in our viewer:

1. **Equirectangular pole pinch (inherent to the asset).** The panorama's
   bottom edge is one row of 4,096 pixels; on the sphere that whole row
   collapses to a single point at the pole. Every row near the pole is
   stretched around the fan, so any cloud near the pole smears into radial
   streaks. This is a property of the projection, not a bug in any renderer:
   "It is generally not possible to map a 2d image onto a sphere and have no
   distortions" (three.js forum, grml).
2. **Low-poly fan geometry (makes the pinch look hard-edged).** The sphere
   is a UV sphere with 64 triangles fanning from a single pole vertex.
   Texture coordinates are interpolated linearly across each triangle, so
   the pinch renders as 64 hard wedges — the visible "starburst". The
   boytchev texture-generator docs describe exactly this: "When textures
   are applied to low-poly spheres there is a noticeable zig-zag distortion
   of the texture shapes, especially near the poles… This phenomena is not
   caused by the texture itself, but by the algorithm that maps the texture
   on a sphere."
3. **Our single-row heal (adds smear on top).** The GLB file is truncated
   (header declares 2,697,556 bytes, file has 2,660,849; the embedded JPEG
   has no EOI marker and ends ~70 rows early). The current fix fills the
   72 missing rows by stretching one good row over them. At the pole that
   one row becomes radial streaks of its own. Measured earlier: the heal
   log reads `[sky] pole check: healed 72 rows sat:0.150 lum:0.480`.

At the horizon none of this matters — the mapping is undistorted there,
which is why our horizon view already matches Sketchfab's presentation.

## 2. This specific model — did anyone else report it?

**No public report found.** Searches for the model together with
pole / zenith / top / distortion / warp return only the model page itself.
The model has 25 comments, 106,686 views and 36,919 downloads (Sketchfab
API, 2026-11-19), but the comments are not readable through any public
route I could reach: the API comments endpoint
(`api.sketchfab.com/v3/models/<uid>/comments`) returns 404, and the model
page's fetched text contains no comment content. So there is no public
evidence either way — nobody has visibly discussed this model's pole.

What the author did include (from the model page and the GLB itself):

- Description: "Anime Sky SkyBox for your scene. It can be used to render
  your scene or in your vr games / apps and environments. Included is the
  panoramic texture in **6k** resolution. *Note: Due to changes in the
  software, I cannot offer an HDRI version of this.* This was generated
  with AI and edited with Blender and Photoshop."
- The material is emissive/unlit by design: `emissiveFactor` white,
  `emissiveTexture` = the panorama, `diffuseFactor` white (1,1,1,1),
  `glossinessFactor` 0.4, `specularFactor` 0. Our unlit rendering matches
  the author's intent.
- The GLB actually carries the texture at 4096×2048, not 6k, and truncated.
  The "6k" is the source panorama before Sketchfab's processing; there is
  no separate pole fix in the model — no cap geometry, no cube faces, just
  the one sphere and the one panoramic texture.
- The author's other skyboxes (e.g. "SkyBox Basic Sky", "SkyBox Enchanted
  Forest") use the same sphere-with-panorama construction, so there is no
  later model from him that demonstrates a different pole treatment.

## 3. Does Sketchfab's viewer do anything special at the pole?

**No evidence that it does.** Sketchfab renders the glTF as authored
through its standard PBR pipeline; nothing in its docs or in the model
page suggests pole correction. The reason the "Sketchfab ideal" looks
clean is presentation, not processing: the model's thumbnail and default
camera are a horizon view from inside the sphere, where the mapping is
undistorted. Looked at straight up from inside, Sketchfab would show the
same pinch — same geometry, same UVs, same texture. (I could not drive
Sketchfab's 3D viewer to confirm the straight-up view directly; that
needs a live browser session, not a text fetch.)

## 4. How the wider world fixes equirect pole pinch

Sources are the three.js forum, PanoCraft's three.js guides, the OpenNews
Mars-globe write-up, and texture-authoring tutorials. The consensus: the
singularity cannot be removed from an equirect texture on a sphere; it can
only be moved, hidden, or softened.

### A. `scene.background` with `EquirectangularReflectionMapping` (three.js)
Assign the texture to `scene.background` instead of putting it on a mesh.
Three.js renders the background by sampling the texture per-pixel from the
view direction — there is no fan geometry, so the pinch becomes a smooth
blur at the pole instead of 64 hard wedges. This is the effect one forum
user reported as reducing distortion "dramatically"
(`texture.mapping = THREE.EquirectangularReflectionMapping`).
- Applicability: **high — the best first fix for our viewer.** The texture
  is already decoded by hand into a canvas; it can be handed to
  `scene.background` instead of to the sphere material, and the sphere mesh
  can be dropped. The palace still renders on top (the background is always
  behind the scene, which is correct for a skybox). Watch the orientation:
  equirect background mapping expects the standard 2:1 orientation, so the
  current `flipY = false` choice has to be re-checked against the rendered
  result (sky up, sun in the right place), and the camera far plane stops
  mattering.
- Sources: https://www.panocraft.si/use-cases/three-js-360-panorama-viewer ;
  https://discourse.threejs.org/t/distortion-on-applying-texture-with-plate-carree-projection-to-sphere/89562

### B. Convert equirect → cube map
Render the panorama into six square faces (px, nx, py, ny, pz, nz) and use
a `CubeTexture` as `scene.background`. A cube has no pole singularity;
the top face is a flat 90° view, so the pinch becomes a mild stretch.
- Applicability: **high, as a build-time step or a one-off runtime
  conversion.** At build time, a tool such as PanoCraft's in-browser
  converter (or the same math in a small script) produces six faces once,
  and the viewer ships them instead of the GLB sphere. At runtime, three.js
  can do it with a CubeCamera render or a PMREM-style pass, but that is
  ~50 lines of new load-time code on a page that is currently simple.
  Either way the six faces must be generated from the *healed* texture, or
  the missing rows reappear on the top face. Note the PanoCraft warning:
  "The poles are where equirectangular resampling is weakest" — even the
  cube top face is a resample of the pinched region, so this softens the
  warp rather than erasing it.
- Sources: https://www.panocraft.si/tools/panorama-to-cubemap ;
  https://www.panocraft.si/use-cases/panorama-to-cubemap-unity-unreal ;
  https://tools.atlyxenstudios.com/equirectangular_to_cubemap/

### C. Paint the pole flat in the texture (the professional workflow)
Convert the panorama to polar coordinates, paint/heal the pole region so
the top rows are a smooth radial gradient or flat sky, convert back — so
that when the texture is pinched, it pinches something featureless. One
skybox author describes it as: create a Python tool to convert the texture
into a cubemap "in order to paint the poles flat. This way, I avoided
getting the infamous pinch at the pole once in engine." The KSP planetary
guide and the Screaming Brain spherical-textures tutorial give the same
procedure with Photoshop/GIMP's Polar Coordinates filter.
- Applicability: **high — and the cheapest fix in our viewer.** Our heal
  already edits the pole band at runtime in a canvas. Replace the
  single-row smear with (i) mirroring the rows above the missing band
  (reflect the last ~70 good rows downward, flipped, so cloud structure
  continues instead of streaking) and (ii) a vertical blur over the pole
  band (top ~8%) so the fan triangles blend. No new assets, no new
  geometry, stays inside the existing `healSkyPoleBand` code path.
  Expected result: the starburst softens into a soft cloudy convergence,
  close to the soft look in Sketchfab's thumbnail. It will not be a
  perfect sky — the pole will still be the blurriest part of the image.
- Sources: https://mcderne.artstation.com/blog/PQMBX/wip-hand-drawn-sky-to-skybox-in-ue ;
  https://forum.kerbalspaceprogram.com/topic/165285-planetary-texturing-guide-repository/ ;
  https://screamingbrainstudios.com/spherical-textures/

### D. Higher-poly sphere / icosphere / cube-sphere geometry
Replace the 64×32 UV sphere with a denser sphere or an icosphere.
- Applicability: **low on its own.** The forum poster tried an icosphere
  and reported "distortions still exist, but of different kinds"; the
  reply: the singularity is in the UV mapping, not the tessellation.
  Denser geometry makes the wedge edges finer but does not remove the
  pinch. A "cube sphere" (subdivided cube projected onto a sphere, six
  textures) is the geometry-side equivalent of the cube map in (B).
- Source: https://discourse.threejs.org/t/distortion-on-applying-texture-with-plate-carree-projection-to-sphere/89562

### E. Shader-level per-pixel equirect sampling on the sphere
Patch the material shader (`onBeforeCompile`) so UVs are computed from
the fragment's view direction instead of interpolated mesh UVs — the
boytchev texture-generator project does exactly this to fix low-poly
sphere distortion.
- Applicability: **medium.** It works, but it re-implements what
  `scene.background` (A) already does, with more invasive code. Only
  worth it if the sphere mesh must be kept for some reason (it doesn't
  need to be — the sky is a background).
- Source: https://boytchev.github.io/texture-generator/docs/about.html

### F. Cheaper texture-sampling tweaks
- `minFilter = THREE.LinearFilter`, `generateMipmaps = false`: the claygl
  skybox code sets linear min filtering on equirect env maps with the
  comment "reduces pole artifacts" — mipmaps at the pole sample across the
  seam and smear it. Our viewer currently generates mipmaps. One-line
  experiment, try alongside (C).
- `texture.anisotropy = renderer.capabilities.getMaxAnisotropy()`: the
  forum's suggestion; helps grazing-angle sampling, marginal at the pole
  itself.
- Source: https://deepwiki.com/pissang/claygl/7.3-skybox-and-environment

### G. Cube-sphere / gnomonic cube mapping (the "proper" geometry fix)
Build the sky from a cube inflated to a sphere, with six gnomonic-projected
faces. The OpenNews Mars-globe write-up shows the before/after: the
plate-carrée sphere pinches at the pole; the inflated cube does not.
- Applicability: **low for this project.** It needs the panorama
  re-projected into six gnomonic faces (same conversion as (B)) plus a
  custom mesh — strictly more work than (B) for the same visual result.
- Source: https://source.opennews.org/articles/how-we-made-rewind-red-planet/

### H. Getting the 6k original texture
The author says a 6k panorama is included; the GLB carries 4k, truncated.
The Sketchfab download archive may contain the original file.
- Applicability: **not a pole fix.** Higher resolution sharpens the pole
  but the singularity is geometric — the same rows still collapse to a
  point. Worth doing only for general sharpness, and it needs a Sketchfab
  account to download the archive. Do not pursue it as the warp fix.

### I. Pole-cap geometry
Add a small disc at the zenith carrying a radial sky gradient.
- Applicability: **not recommended.** It hides the pinch behind a disc
  whose edge is visible unless the colour match is perfect; (C) achieves
  the same hiding with no new geometry.

### J. Clamp the camera pitch so nobody can look straight up
PanoCraft's guide clamps pitch to ±90°; the Orrery RFC notes pole
distortion "doesn't matter for Apollo panoramas (the photographer never
looked straight up or down)".
- Applicability: **not a fix — a dodge.** Pol already looks straight up
  and reported the warp. Hiding the angle instead of fixing the render
  would just move the complaint.

## 5. Recommendation for our viewer

Two changes, in order of effort:

1. **Minimal (an afternoon): (C) + (F).** Improve `healSkyPoleBand` to
   mirror-then-blur the pole band instead of smearing one row, and turn
   mipmaps off for the sky texture. Expected: the starburst softens into
   a cloudy convergence; the pole stays the softest part of the sky.
2. **Proper (the real fix): (A), optionally with (B).** Drop the sphere
   mesh and put the healed texture on `scene.background` with
   `EquirectangularReflectionMapping` — per-pixel sampling removes the
   fan wedges entirely. If the pole still reads as a soft smudge, bake
   the texture to six cube faces (B) once at build time and use the cube
   as the background. Either step keeps the page static and keeps the
   hand-decoded-texture code path (only the final assignment changes).

What is *not* worth doing: chasing the 6k original (H), a pole-cap disc
(I), clamping the camera (J), or re-tessellating the sphere (D) on its own.
