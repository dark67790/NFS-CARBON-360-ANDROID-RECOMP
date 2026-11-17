import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
if "carbon-ws2" in s:
    print("already patched")
    sys.exit(0)
if "carbon-widescreen" in s:
    sys.exit("the OLD widescreen step already patched this file: remove it from the workflow and keep only this one")

def once(old, new, what):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit("ANCHOR %s: expected 1, found %d" % (what, n))
    s = s.replace(old, new)

once('#include "nfsmw_nativo_sistema.h"\n',
     '#include <cmath>\n#include <SDL3/SDL_video.h>\n#include "nfsmw_nativo_sistema.h"\n', "include")

once('namespace {\nconstexpr uint32_t kRenderer = 0x82C65304;',
     '''// carbon-ws2: the game draws at the screen's proportion (scene mode width = height * carbon_aspect) and the
// camera sees more at the sides (Hor+) instead of cropping top and bottom. HUD, menus and videos are stretched.
REXCVAR_DEFINE_DOUBLE(carbon_aspect, 0.0, "Carbon/Android",
                      "Screen width / height (2.2222 on a 20:9 phone) to draw the game at that proportion, wider "
                      "view at the sides. 0 or below 1.9 = 16:9 like the Xbox 360. Up to 2.6. Needs carbon_single_pass")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(carbon_widescreen, false, "Carbon/Android",
                    "Draw the game at the screen's own proportion, read from the display (nothing happens on a 16:9 "
                    "screen). carbon_aspect, if set, wins over this")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
REXCVAR_DEFINE_BOOL(carbon_aspect_camera, true, "Carbon/Android",
                    "With carbon_aspect: widen the camera (Hor+). Off = same camera, only the picture is stretched")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

namespace {
constexpr uint32_t kRenderer = 0x82C65304;''', "namespace")

once('std::pair<uint32_t, uint32_t> Size() {',
     'std::pair<uint32_t, uint32_t> BaseSize() {', "Size def")

once('void OutputSize(uint8_t* base) {',
     '''// The proportion to draw at (0 = plain 16:9): carbon_aspect, or the display's with carbon_widescreen. Decided once, at
// the first call, so every size the game is given in a run agrees.
double WideAspect() {
  static const double decided = []() -> double {
    const double manual = REXCVAR_GET(carbon_aspect);
    if (manual >= 1.9) return std::min(manual, 2.6);
    if (!REXCVAR_GET(carbon_widescreen)) return 0.0;
    const SDL_DisplayID display = SDL_GetPrimaryDisplay();
    const SDL_DisplayMode* mode = display ? SDL_GetCurrentDisplayMode(display) : nullptr;
    if (!mode || mode->w <= 0 || mode->h <= 0) {
      REXLOG_WARN("[carbon] widescreen: cannot read the display size, staying at 16:9 (use carbon_aspect)");
      return 0.0;
    }
    const double aspect = double(std::max(mode->w, mode->h)) / double(std::min(mode->w, mode->h));
    REXLOG_INFO("[carbon] widescreen: display {}x{} -> proportion {:.4f}{}", mode->w, mode->h, aspect,
                aspect >= 1.9 ? "" : " (16:9 or narrower: the game as it is)");
    return aspect >= 1.9 ? std::min(aspect, 2.6) : 0.0;
  }();
  return decided;
}
std::pair<uint32_t, uint32_t> Size() {
  auto [width, height] = BaseSize();
  const double aspect = WideAspect();
  if (aspect >= 1.9 && REXCVAR_GET(carbon_single_pass))
    width = uint32_t(std::lround(double(height) * std::min(aspect, 2.6) / 32.0)) * 32u;
  return {width, height};
}
// How much wider than the 16:9 of the same height the scene is (1.25 for 1600x720); 1 = off.
double WideFactor() {
  auto [width, height] = Size();
  const double k = double(width) / (double(height) * 16.0 / 9.0);
  return k > 1.02 ? k : 1.0;
}
void OutputSize(uint8_t* base) {''', "OutputSize")

s += r'''
// carbon-ws2: Hor+ camera. sub_822CEC80(r3 = view block, r4 = eView, f1 = ...) writes the projection at
// block+64 and a copy at block+128 ([0][0] = 1 / tan(horizontal) at +0, [1][1] = -1 / tan(vertical) at +20), then calls
// sub_822CEA90 (its only caller), which returns H (LOD / culling) for eView+16, and then multiplies the view by the
// projection. The vertical angle is proportional to height / width of the view's render target (table 0x82C721D0,
// 480 bytes per view id [eView+8], target object at +464 with width at +16 and height at +20; 640x480 if none).
// For the views drawn at the wide size: [0][0] / k (wider), the vertical angle * k (back to the 16:9 one), H / k.
namespace {
thread_local uint32_t t_block = 0;
thread_local uint32_t t_view = 0;

uint32_t WRead32(const uint8_t* base, uint32_t address) {
  uint32_t v;
  std::memcpy(&v, base + address, sizeof(v));
  return __builtin_bswap32(v);
}
float WReadFloat(const uint8_t* base, uint32_t address) {
  const uint32_t v = WRead32(base, address);
  float f;
  std::memcpy(&f, &v, sizeof(f));
  return f;
}
void WWriteFloat(uint8_t* base, uint32_t address, float f) {
  uint32_t v;
  std::memcpy(&v, &f, sizeof(v));
  v = __builtin_bswap32(v);
  std::memcpy(base + address, &v, sizeof(v));
}
bool CameraCodeIsCarbon(const uint8_t* base) {
  static int state = 0;  // 0 not checked, 1 ok, 2 different
  if (!state) {
    state = (WRead32(base, 0x822CEC80) == 0x7D8802A6 && WRead32(base, 0x822CEC84) == 0x484CC2A5) ? 1 : 2;
    if (state == 2) REXLOG_WARN("[carbon] widescreen camera: sub_822CEC80 is not the expected code, camera not changed");
  }
  return state == 1;
}
// k for this view (1 = leave it), from the size of the view's target.
double WideViewFactor(const uint8_t* base, uint32_t view) {
  const double k = WideFactor();
  if (k <= 1.0) return 1.0;
  const uint32_t id = WRead32(base, view + 8);
  if (id > 255) return 1.0;
  const uint32_t target = WRead32(base, 0x82C721D0 + 480 * id + 464);
  const uint32_t width = target ? WRead32(base, target + 16) : 640;
  const uint32_t height = target ? WRead32(base, target + 20) : 480;
  auto [wide_width, wide_height] = Size();
  const double wanted = double(wide_width) / double(wide_height);
  static uint64_t seen = 0;
  if (id < 64 && !(seen & (uint64_t(1) << id))) {
    seen |= uint64_t(1) << id;
    REXLOG_INFO("[carbon] widescreen: view {} target {}x{} (wide scene {}x{}, k {:.4f})", id, width, height,
                wide_width, wide_height, k);
  }
  if (height == 0 || std::fabs(double(width) / double(height) - wanted) > wanted * 0.05) return 1.0;
  if (width != wide_width && width * 2 != wide_width && width * 4 != wide_width) return 1.0;
  return k;
}
void WideProjection(uint8_t* base, uint32_t projection, double k) {
  const float sx = WReadFloat(base, projection + 0);
  const float sy = WReadFloat(base, projection + 20);
  if (!(sx > 0.0f) || sy == 0.0f || !std::isfinite(sx) || !std::isfinite(sy)) return;
  const double vertical = std::min(std::atan(1.0 / std::fabs(double(sy))) * k, 1.55);  // under 89 degrees
  WWriteFloat(base, projection + 0, float(double(sx) / k));
  WWriteFloat(base, projection + 20, float(std::copysign(1.0 / std::tan(vertical), double(sy))));
}
}  // namespace

REX_EXTERN(__imp__sub_822CEC80);
REX_HOOK_RAW(sub_822CEC80) {
  t_block = ctx.r3.u32;
  t_view = ctx.r4.u32;
  __imp__sub_822CEC80(ctx, base);
  t_block = 0;
  t_view = 0;
}

REX_EXTERN(__imp__sub_822CEA90);
REX_HOOK_RAW(sub_822CEA90) {
  __imp__sub_822CEA90(ctx, base);
  if (t_block && t_view && verified && REXCVAR_GET(carbon_aspect_camera) && CameraCodeIsCarbon(base)) {
    const double k = WideViewFactor(base, t_view);
    if (k > 1.0) {
      WideProjection(base, t_block + 64, k);
      WideProjection(base, t_block + 128, k);
      ctx.f1.f64 /= k;  // H as at 16:9: the same LOD and culling distances
      static int logged = 0;
      if (logged++ < 4) REXLOG_INFO("[carbon] widescreen camera: view block {:08X} corrected, k {:.4f}", t_block, k);
    }
  }
}
'''
open(p, "w", encoding="utf-8").write(s)
print("patched")
