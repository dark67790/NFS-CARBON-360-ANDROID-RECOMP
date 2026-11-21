import os, sys

# Usage: streaming.py <repo root>
# Adds the streaming anticipation fix (src/carbon_streaming_anticipacion.cpp) and lists it in CMakeLists.txt.
root = sys.argv[1]
src_path = os.path.join(root, "src", "carbon_streaming_anticipacion.cpp")
cmake_path = os.path.join(root, "CMakeLists.txt")

SRC = r'''// carbon-stream: the streamer asks for the next track section too late.
//
// Ported from NFS Most Wanted Android Evolved (nfsmw_streaming_anticipacion.cpp). Same game code, other addresses.
//
// TrackStreamer::GetPredictedZone looks 1.5 s ahead of the player and never more than 100 m. At 25 m/s (a corner or an
// alley) that is 37 m, so the section that is about to be needed is requested late: popping, plus a burst of texture
// creation in one frame (the hitch around corners).
//
// Carbon's addresses (found with the instruction pattern of the original, see docs):
//   sub_825814D0 = GetPredictedZone(StreamingPositionEntry* r4) -> short zone
//   sub_8257D700 = TrackPathManager::FindZone(this r3, bVector2* r4, type r5 = 6, previous zone r6)
//   0x8205E480 = 1.5f   seconds of lookahead
//   0x820638DC = 100.0f cap in metres
//   0x820C84E0 = max speed above which the game does not predict
// Entry layout (from the disassembly): Position x,y,z at +0, Velocity x,y,z at +16 (speed = |Velocity|, 3D),
// the position FindZone is queried with is entry+48.
//
// How: the game reads the velocity twice, once for the speed (stays in f3) and once, after the first FindZone call,
// to build the offset. The real velocity is left in place at entry, and a longer fake one is written right after
// FindZone returns; the original code then predicts further ahead with its own constants. Velocity is always
// restored on exit. If the constants do not look like 1.5 s / 100 m the whole thing switches itself off.
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>

#include <rex/cvar.h>
#include <rex/hook.h>
#include <rex/logging.h>

REXCVAR_DEFINE_INT32(carbon_streaming_anticipacion, 250, "Carbon/Android",
                     "Percent of the streamer's lookahead. 100 = the original game (1.5 s ahead, max 100 m). "
                     "250 = looks 2.5x further. Fixes late section loading at corners (popping / hitches)")
    .range(100, 600);
REXCVAR_DEFINE_INT32(carbon_streaming_techo_m, 160, "Carbon/Android",
                     "Max metres the streamer may look ahead. 0 = the game's own cap (100 m)")
    .range(0, 400);
REXCVAR_DEFINE_BOOL(carbon_streaming_diag, true, "Carbon/Android",
                    "Also run the prediction without the extra lookahead, to compare and to fall back if the "
                    "longer lookahead finds no zone");

namespace carbon_stream {
namespace {

constexpr uint32_t kDirSegundos = 0x8205E480;  // 1.5f
constexpr uint32_t kDirTecho = 0x820638DC;     // 100.0f
constexpr uint32_t kDirVelMax = 0x820C84E0;    // speed above which there is no prediction

constexpr uint32_t kOffVelX = 16;
constexpr uint32_t kOffVelY = 20;
constexpr uint32_t kOffVelZ = 24;
constexpr uint32_t kOffPosFindZone = 48;  // pointer the first FindZone call receives in r4

constexpr uint32_t kDireccionMaxima = 0xE0000000u;
constexpr uint32_t kCadaCuantasLineas = 1024;
constexpr float kSegundosMin = 0.1f, kSegundosMax = 10.0f;
constexpr float kTechoMin = 10.0f, kTechoMax = 2000.0f;
constexpr float kLongitudFalsaMax = 1000.0f;

uint32_t Leer32(const uint8_t* base, uint32_t dir) {
  uint32_t v = 0;
  std::memcpy(&v, base + dir, sizeof(v));
  return __builtin_bswap32(v);
}
float LeerFlotante(const uint8_t* base, uint32_t dir) {
  const uint32_t v = Leer32(base, dir);
  float f = 0.0f;
  std::memcpy(&f, &v, sizeof(f));
  return f;
}
void EscribirFlotante(uint8_t* base, uint32_t dir, float f) {
  uint32_t v = 0;
  std::memcpy(&v, &f, sizeof(v));
  v = __builtin_bswap32(v);
  std::memcpy(base + dir, &v, sizeof(v));
}

thread_local uint32_t t_entrada = 0;
thread_local float t_vel[3] = {0, 0, 0};
thread_local bool t_armado = false;
thread_local bool t_aplicado = false;

std::atomic<bool> g_presentado{false};
std::atomic<bool> g_constantes_mal{false};
std::atomic<uint64_t> g_llamadas{0}, g_actuadas{0}, g_aplicadas{0}, g_distintas{0}, g_rescates{0}, g_sin_relevo{0};
std::atomic<uint64_t> g_suma_antes_mm{0}, g_suma_despues_mm{0};

void QuizaImprimir() {
  const uint64_t n = g_llamadas.load(std::memory_order_relaxed);
  if (n == 0 || (n % kCadaCuantasLineas) != 0) return;
  const uint64_t act = g_actuadas.load(std::memory_order_relaxed);
  const double antes = act ? double(g_suma_antes_mm.load(std::memory_order_relaxed)) / act / 1000.0 : 0.0;
  const double desp = act ? double(g_suma_despues_mm.load(std::memory_order_relaxed)) / act / 1000.0 : 0.0;
  REXLOG_INFO(
      "[stream] {} calls, {} with extra lookahead, {} applied ({} not applied); looks {:.1f} m -> {:.1f} m on average; "
      "{} different zones requested; {} fallbacks",
      n, act, g_aplicadas.load(std::memory_order_relaxed), g_sin_relevo.load(std::memory_order_relaxed), antes, desp,
      g_distintas.load(std::memory_order_relaxed), g_rescates.load(std::memory_order_relaxed));
}

}  // namespace
}  // namespace carbon_stream

// TrackPathManager::FindZone(this, bVector2* pos, type, prev). Only does something inside the armed
// GetPredictedZone call, when pos is the one of the entry being predicted.
REX_EXTERN(__imp__sub_8257D700);
REX_HOOK_RAW(sub_8257D700) {
  using namespace carbon_stream;
  const uint32_t arg = ctx.r4.u32;  // read before the call: the original clobbers r4
  __imp__sub_8257D700(ctx, base);
  if (!t_armado || arg == 0 || arg != t_entrada + kOffPosFindZone) return;
  EscribirFlotante(base, t_entrada + kOffVelX, t_vel[0]);
  EscribirFlotante(base, t_entrada + kOffVelY, t_vel[1]);
  EscribirFlotante(base, t_entrada + kOffVelZ, t_vel[2]);
  t_aplicado = true;
}

// TrackStreamer::GetPredictedZone(StreamingPositionEntry* r4) -> short
REX_EXTERN(__imp__sub_825814D0);
REX_HOOK_RAW(sub_825814D0) {
  using namespace carbon_stream;

  g_llamadas.fetch_add(1, std::memory_order_relaxed);
  const int32_t mult_pct = REXCVAR_GET(carbon_streaming_anticipacion);
  const int32_t techo_cvar = REXCVAR_GET(carbon_streaming_techo_m);
  const uint32_t entrada = ctx.r4.u32;

  auto original = [&]() {
    __imp__sub_825814D0(ctx, base);
    QuizaImprimir();
  };

  if (mult_pct <= 100 || g_constantes_mal.load(std::memory_order_relaxed) || entrada == 0 ||
      entrada + kOffPosFindZone + 16u >= kDireccionMaxima) {
    original();
    return;
  }

  const float k_seg = LeerFlotante(base, kDirSegundos);
  const float k_techo = LeerFlotante(base, kDirTecho);
  const float k_vmax = LeerFlotante(base, kDirVelMax);
  if (!(k_seg >= kSegundosMin && k_seg <= kSegundosMax) || !(k_techo >= kTechoMin && k_techo <= kTechoMax) ||
      !(k_vmax > 10.0f && k_vmax < 10000.0f)) {
    if (!g_constantes_mal.exchange(true)) {
      REXLOG_WARN("[stream] constants do not match (seconds={} cap={} vmax={}): extra lookahead DISABLED, game unchanged",
                  double(k_seg), double(k_techo), double(k_vmax));
    }
    original();
    return;
  }
  if (!g_presentado.exchange(true)) {
    REXLOG_INFO(
        "[stream] game looks {:.2f} s ahead, never more than {:.1f} m, no prediction above {:.1f} m/s; "
        "with carbon_streaming_anticipacion={} % and carbon_streaming_techo_m={} it is asked to look further",
        double(k_seg), double(k_techo), double(k_vmax), mult_pct, techo_cvar);
  }

  const float vx = LeerFlotante(base, entrada + kOffVelX);
  const float vy = LeerFlotante(base, entrada + kOffVelY);
  const float vz = LeerFlotante(base, entrada + kOffVelZ);
  const float s = std::sqrt(vx * vx + vy * vy + vz * vz);
  if (!std::isfinite(s) || s <= 1.0f || s > k_vmax) {  // stopped, or above the speed where the game stops predicting
    original();
    return;
  }

  const float techo = techo_cvar > 0 ? float(techo_cvar) : k_techo;
  const float antes = std::min(k_seg * s, k_techo);
  const float despues = std::min(k_seg * s * (float(mult_pct) / 100.0f), techo);
  if (!(despues > antes + 0.5f)) {
    original();
    return;
  }

  // The game picks the branch with the real speed (f3):
  //   cap branch    (s*k_seg  > k_techo): predict = pos + v * (k_techo / s)
  //   normal branch (s*k_seg <= k_techo): predict = pos + v * k_seg
  // Length of the fake vector so the projected distance is exactly "despues".
  float largo = (k_seg * s > k_techo) ? (despues * s / k_techo) : (despues / k_seg);
  if (!std::isfinite(largo) || largo <= 0.0f) {
    original();
    return;
  }
  largo = std::min(largo, kLongitudFalsaMax);

  t_entrada = entrada;
  t_vel[0] = vx / s * largo;
  t_vel[1] = vy / s * largo;
  t_vel[2] = vz / s * largo;
  t_aplicado = false;

  const bool diag = REXCVAR_GET(carbon_streaming_diag);
  int32_t zona_base = 0;
  if (diag) {
    const uint64_t r3_orig = ctx.r3.u64;
    const uint64_t r4_orig = ctx.r4.u64;
    const uint64_t lr_orig = ctx.lr;
    t_armado = false;
    __imp__sub_825814D0(ctx, base);
    zona_base = int32_t(int16_t(uint16_t(ctx.r3.u32)));
    ctx.r3.u64 = r3_orig;
    ctx.r4.u64 = r4_orig;
    ctx.lr = lr_orig;
  }

  t_armado = true;
  __imp__sub_825814D0(ctx, base);
  t_armado = false;

  EscribirFlotante(base, entrada + kOffVelX, vx);
  EscribirFlotante(base, entrada + kOffVelY, vy);
  EscribirFlotante(base, entrada + kOffVelZ, vz);
  t_entrada = 0;

  g_actuadas.fetch_add(1, std::memory_order_relaxed);
  g_suma_antes_mm.fetch_add(uint64_t(antes * 1000.0f), std::memory_order_relaxed);
  g_suma_despues_mm.fetch_add(uint64_t(despues * 1000.0f), std::memory_order_relaxed);
  if (t_aplicado) {
    g_aplicadas.fetch_add(1, std::memory_order_relaxed);
  } else {
    g_sin_relevo.fetch_add(1, std::memory_order_relaxed);
  }

  if (diag) {
    const int32_t zona_ade = int32_t(int16_t(uint16_t(ctx.r3.u32)));
    if (zona_ade != zona_base) {
      g_distintas.fetch_add(1, std::memory_order_relaxed);
      // The longer lookahead found no zone: give back the game's own answer, never worse than the original.
      if (zona_base != 0 && zona_ade == 0) {
        ctx.r3.s64 = int64_t(int16_t(zona_base));
        g_rescates.fetch_add(1, std::memory_order_relaxed);
      }
    }
  }
  QuizaImprimir();
}
'''

with open(src_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(SRC)
print("wrote", src_path)

s = open(cmake_path, encoding="utf-8").read()
if "carbon_streaming_anticipacion.cpp" in s:
    print("CMakeLists already lists it")
    sys.exit(0)
old = "target_sources(nfscarbon PRIVATE\n    src/carbon_nativo_ganchos.cpp\n"
if s.count(old) != 1:
    sys.exit("ANCHOR not found in CMakeLists.txt (expected 1, found %d)" % s.count(old))
s = s.replace(old, old + "    src/carbon_streaming_anticipacion.cpp\n")
open(cmake_path, "w", encoding="utf-8", newline="\n").write(s)
print("CMakeLists.txt patched")
