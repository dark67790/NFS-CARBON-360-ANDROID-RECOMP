
#!/usr/bin/env python3
"""GSR 2 (victorgbd's port for Most Wanted) onto the pinned nfsmw-android + Carbon.
usage: patch.py NFS_ROOT CARBON_ROOT MW_NATIVO_DIR
Idempotent (marker carbon-gsr2), strict anchors (exactly one match or fail)."""
import sys, os, shutil

NFS, C, MW = sys.argv[1], sys.argv[2], sys.argv[3]
APP = NFS + "/app/src"
SDK = NFS + "/sdk"


def rd(p):
    return open(p, encoding="utf-8").read()


def wr(p, s):
    open(p, "w", encoding="utf-8").write(s)


def once(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit("ANCHOR %s: expected 1, found %d" % (what, n))
    return s.replace(old, new)


# carbon-gsr2: the frame bracket (block comments only: nothing here starts a line with "//")
HOOK_BLOCK = r"""
/* carbon-gsr2: one camera and one jitter phase per frame. sub_82453428 is the render thread's main loop (init, then a
   loop that calls sub_82453048 once per frame with the elapsed time; nothing else calls it): that call is one frame.
   Inside it: sub_82452E70 -> sub_8250AD38 -> sub_8250AE40 -> sub_822CEC80 (the views' update). */
REX_EXTERN(__imp__sub_82453048);
REX_HOOK_RAW(sub_82453048) {
  nfsmw::gsr2::EmpezarLlenado();
  __imp__sub_82453048(ctx, base);
  nfsmw::gsr2::TerminarLlenado();
}
"""

# ---------------------------------------------------------------- 1. files from victorgbd's repo
for rel in ("app/src/nfsmw_gsr2.cpp", "app/src/nfsmw_gsr2.h",
            "app/src/shaders/nfsmw_sgsr2_convertir_ps.h", "app/src/shaders/nfsmw_sgsr2_escalar_ps.h"):
    src = MW + "/" + rel
    if not os.path.isfile(src):
        sys.exit("missing in victorgbd's checkout: " + src)
os.makedirs(APP + "/shaders", exist_ok=True)
g = APP + "/nfsmw_gsr2.cpp"
if os.path.exists(g) and "carbon-gsr2" in rd(g):
    print("gsr2 sources already carbonised")
else:
    for rel in ("app/src/nfsmw_gsr2.cpp", "app/src/nfsmw_gsr2.h",
                "app/src/shaders/nfsmw_sgsr2_convertir_ps.h", "app/src/shaders/nfsmw_sgsr2_escalar_ps.h"):
        shutil.copyfile(MW + "/" + rel, NFS + "/" + rel)
    s = rd(g)
    s = once(s, "constexpr uint32_t kTablaPases = 0x82C3F590;  // nfsmw_panoramico.cpp",
             "constexpr uint32_t kTablaPases = 0x82C721D0;  // carbon-gsr2: Carbon's view table (stride 480)", "tabla")
    s = once(s, "constexpr uint32_t kBytesPorPase = 384;", "constexpr uint32_t kBytesPorPase = 480;", "bytes")
    s = once(s, "constexpr uint32_t kOffDestino = 368;", "constexpr uint32_t kOffDestino = 464;", "offdest")
    s = once(s, "  const uint32_t id = Leer32(base, vista + 4);\n", "  const uint32_t id = Leer32(base, vista + 8);  // Carbon: view id at eView+8\n", "id")
    s = once(s, "Leer32(base, vista + 4) != kVistaEscena", "Leer32(base, vista + 8) != kVistaEscena", "id2")
    s = once(s, "c.vp[i] = double(LeerFloat(base, bloque + 128 + i * 4));",
             "c.vp[i] = double(LeerFloat(base, bloque + 192 + i * 4));  // Carbon: view x projection at block+192", "vp")
    wr(g, s)
    print("gsr2 sources copied and carbonised")


# carbon-gsr2 (2nd round): the 2D-only frame flag. Separate from the copy above because those files stay on the
# runner (untracked) and an earlier run may have carbonised them already.
g = APP + "/nfsmw_gsr2.cpp"
h = APP + "/nfsmw_gsr2.h"
s = rd(g)
if "e.solo_2d" not in s:
    s = once(s, "    reset = reset || !camara.valida || !anterior_.valida;\n",
             "    reset = reset || !camara.valida || !anterior_.valida || e.solo_2d;  // carbon-gsr2: a frame of 2D only has nothing to accumulate\n", "solo2d use")
    wr(g, s)
sh = rd(h)
if "solo_2d" not in sh:
    sh = once(sh, "  bool escena_rb = false;  // red and blue swapped relative to color\n",
              "  bool escena_rb = false;  // red and blue swapped relative to color\n"
              "  bool solo_2d = false;    // carbon-gsr2: no 3D draw this frame (menus): no history, just the upscale\n", "solo2d field")
    wr(h, sh)
    print("gsr2 2D-only flag added")

# carbon-gsr2 (3rd round, reverted): an earlier build replaced the upscale shader with a HUD-smoothing one and added a
# debug cvar. Victorgbd's original shader is used as it is: put it back (and take the cvar out) where it was installed.
hdr = APP + "/shaders/nfsmw_sgsr2_escalar_ps.h"
if "HUD smooth upscale" in rd(hdr):
    shutil.copyfile(MW + "/app/src/shaders/nfsmw_sgsr2_escalar_ps.h", hdr)
    print("gsr2 original upscale shader restored")
s = rd(g)
if "nfsmw_gsr2_depurar" in s:
    s = once(s, "REXCVAR_DEFINE_INT32(nfsmw_gsr2_depurar, 0, \"NFSMW\",\n"
             "                     \"Snapdragon GSR 2, depuracion: 1 = el HUD detectado en rojo, 2 = el fotograma del juego sin GSR 2 \"\n"
             "                     \"(solo ampliado). 0 = normal\");\n\n", "", "depurar cvar out")
    s = once(s, "    p.relleno1 = float(REXCVAR_GET(nfsmw_gsr2_depurar));  // carbon-gsr2: the upscale shader's debug view\n", "", "depurar use out")
    wr(g, s)
    print("gsr2 debug cvar removed")

# ---------------------------------------------------------------- 2. SDK
p = SDK + "/src/kernel/xboxkrnl/xboxkrnl_video.cpp"
s = rd(p)
if "carbon-gsr2" not in s:
    s = once(s, "void VdSwap_entry(mapped_void buffer_ptr,",
             "// carbon-gsr2: if the app sets it, VdSwap writes what it returns as a fifth word of PM4_XE_SWAP (the game frame).\n"
             "uint32_t (*g_nfsmw_secuencia_swap)() = nullptr;\n\nvoid VdSwap_entry(mapped_void buffer_ptr,", "vdswap1")
    s = once(s, "  dwords[offset++] = xenos::MakePacketType3(xenos::PM4_XE_SWAP, 4);\n",
             "  uint32_t (*const secuencia)() = g_nfsmw_secuencia_swap;\n"
             "  dwords[offset++] = xenos::MakePacketType3(xenos::PM4_XE_SWAP, secuencia ? 5 : 4);\n", "vdswap2")
    s = once(s, "  dwords[offset++] = *width;\n  dwords[offset++] = *height;\n",
             "  dwords[offset++] = *width;\n  dwords[offset++] = *height;\n  if (secuencia) {\n    dwords[offset++] = secuencia();\n  }\n", "vdswap3")
    wr(p, s)
    print("patched xboxkrnl_video.cpp")

p = SDK + "/include/rex/ui/presenter.h"
s = rd(p)
if "carbon-gsr2" not in s:
    s = once(s, "  bool RefreshGuestOutput(uint32_t frontbuffer_width, uint32_t frontbuffer_height,\n"
                "                          uint32_t display_aspect_ratio_x, uint32_t display_aspect_ratio_y,\n"
                "                          std::function<bool(GuestOutputRefreshContext& context)> refresher);\n",
             "  bool RefreshGuestOutput(uint32_t frontbuffer_width, uint32_t frontbuffer_height,\n"
             "                          uint32_t display_aspect_ratio_x, uint32_t display_aspect_ratio_y,\n"
             "                          std::function<bool(GuestOutputRefreshContext& context)> refresher);\n"
             "  // carbon-gsr2: the size of the surface painting is connected to (0 x 0 if none). Any thread.\n"
             "  void GetPaintSurfaceSize(uint32_t& width_out, uint32_t& height_out) const {\n"
             "    width_out = paint_surface_width_.load(std::memory_order_relaxed);\n"
             "    height_out = paint_surface_height_.load(std::memory_order_relaxed);\n"
             "  }\n", "presenter.h accessor")
    s = once(s, "  uint32_t surface_width_in_paint_connection_ = 0;\n  uint32_t surface_height_in_paint_connection_ = 0;\n",
             "  uint32_t surface_width_in_paint_connection_ = 0;\n  uint32_t surface_height_in_paint_connection_ = 0;\n"
             "  std::atomic<uint32_t> paint_surface_width_{0};  // carbon-gsr2\n  std::atomic<uint32_t> paint_surface_height_{0};\n",
             "presenter.h members")
    if "#include <atomic>" not in s:
        s = once(s, "#include <functional>\n", "#include <atomic>\n#include <functional>\n", "presenter.h include")
    wr(p, s)
    print("patched presenter.h")

p = SDK + "/src/ui/presenter.cpp"
s = rd(p)
if "carbon-gsr2" not in s:
    s = once(s, "  surface_width_in_paint_connection_ = 0;\n  surface_height_in_paint_connection_ = 0;\n}\n",
             "  surface_width_in_paint_connection_ = 0;\n  surface_height_in_paint_connection_ = 0;\n"
             "  paint_surface_width_.store(0, std::memory_order_relaxed);  // carbon-gsr2\n"
             "  paint_surface_height_.store(0, std::memory_order_relaxed);\n}\n", "presenter.cpp disconnect")
    s = once(s, "          surface_width_in_paint_connection_ = surface_width;\n          surface_height_in_paint_connection_ = surface_height;\n",
             "          surface_width_in_paint_connection_ = surface_width;\n          surface_height_in_paint_connection_ = surface_height;\n"
             "          paint_surface_width_.store(surface_width, std::memory_order_relaxed);  // carbon-gsr2\n"
             "          paint_surface_height_.store(surface_height, std::memory_order_relaxed);\n", "presenter.cpp connect")
    wr(p, s)
    print("patched presenter.cpp")

# ---------------------------------------------------------------- 3. sistema (the Swap packet)
p = APP + "/nfsmw_nativo_sistema.cpp"
s = rd(p)
if "carbon-gsr2" not in s:
    s = once(s, '#include "nfsmw_esperas_tiron.h"\n', '#include "nfsmw_esperas_tiron.h"\n#include "nfsmw_gsr2.h"  // carbon-gsr2\n', "sistema include")
    s = once(s, "          swap_alto_.store(datos.Leer(), std::memory_order_relaxed);\n        }\n        TrazaSwap();\n",
             "          swap_alto_.store(datos.Leer(), std::memory_order_relaxed);\n        }\n"
             "        nfsmw::gsr2::SwapEnAnillo(palabras >= 5 ? datos.Leer() : 0);  // carbon-gsr2: the game frame of this Swap\n"
             "        TrazaSwap();\n", "sistema swap")
    wr(p, s)
    print("patched nfsmw_nativo_sistema.cpp")

# ---------------------------------------------------------------- 4. destinos
p = APP + "/nfsmw_nativo_destinos.cpp"
s = rd(p)
if "carbon-gsr2" in s:
    print("destinos already patched")
else:
    s = once(s, '#include "nfsmw_ajustes_graficos.h"\n', '#include "nfsmw_ajustes_graficos.h"\n#include "nfsmw_gsr2.h"  // carbon-gsr2\n', "inc")
    s = once(s, "// C2 report of readbacks per render target (base and size) and cadence of nfsmw_nativo_lecturas_cada.\nstruct DestinoLectura {",
             "// carbon-gsr2: one resolve of the frame (Copiar), to find the scene, the composited scene before the HUD and the\n"
             "// depth target when presenting.\n"
             "struct ResolucionFotograma {\n"
             "  uint32_t destino = 0;      // resolved texture address\n"
             "  uint64_t origen = 0;       // render target key (base, format, pitch), as in destinos_\n"
             "  uint32_t pitch = 0;\n"
             "  uint32_t info_profundidad = 0;  // RB_DEPTH_INFO at that moment\n"
             "  int32_t x0 = 0, y0 = 0, x1 = 0, y1 = 0;  // the copied rectangle of the render target\n"
             "  uint32_t ancho = 0, alto = 0;  // the resolved texture's size\n"
             "  bool intercambio_rb = false;\n"
             "};\n"
             "constexpr size_t kResolucionesFotogramaMax = 64;\n\n"
             "// carbon-gsr2: what Presentar hands PintarSalida (the color image and its size are filled in there).\n"
             "struct PlanGsr2 {\n"
             "  bool activo = false;\n"
             "  uint32_t ancho_salida = 0, alto_salida = 0;\n"
             "  nfsmw::gsr2::EntradasVulkan entradas;\n"
             "};\n\n"
             "// C2 report of readbacks per render target (base and size) and cadence of nfsmw_nativo_lecturas_cada.\nstruct DestinoLectura {",
             "structs")
    s = once(s, "#include <rex/graphics/xenos.h>\n", "#include <rex/graphics/registers.h>\n#include <rex/graphics/xenos.h>\n", "regs inc")
    s = once(s, "namespace xenos = rex::graphics::xenos;\n", "namespace xenos = rex::graphics::xenos;\nnamespace gr = rex::graphics;\n", "gr alias")
    s = once(s, "  bool Dibujar(const PeticionDibujo& peticion) override {\n",
             "  bool Dibujar(const PeticionDibujo& peticion) override {\n"
             "    if (gsr_rt_ != 0) {\n"
             "      GsrAntesDeDibujo(peticion);  // carbon-gsr2: the scene before the HUD\n"
             "    }\n", "dibujar hook")
    s = once(s, "    AnotarAreaUtil(*destino_render, y1);\n",
             "    GsrAntesDeResolver(*destino_render, info_color & 0xFFF, pitch);  // carbon-gsr2\n"
             "    AnotarAreaUtil(*destino_render, y1);\n", "copiar hook")
    s = once(s, "  ~DestinosVulkan() override {\n    EsperarGpu();\n",
             "  ~DestinosVulkan() override {\n    EsperarGpu();\n    gsr2_.reset();  // carbon-gsr2: waits for the outputs; uses vs_ and sampler_\n", "dtor")
    s = once(s, '    REXLOG_INFO("[nativo] C2: rampa de gamma del juego en la salida (nfsmw_nativo_rampa_gamma) = {}",\n'
                '                rampa_gamma_ ? "SI" : "no");\n',
             '    REXLOG_INFO("[nativo] C2: rampa de gamma del juego en la salida (nfsmw_nativo_rampa_gamma) = {}",\n'
             '                rampa_gamma_ ? "SI" : "no");\n'
             "    if (nfsmw::gsr2::Activo()) {  // carbon-gsr2\n"
             "      gsr2_ = nfsmw::gsr2::Gsr2Vulkan::Crear(\n"
             "          dispositivo_, vs_, sampler_, kRanurasSalida,\n"
             "          [](void* yo) { static_cast<DestinosVulkan*>(yo)->EsperarSalidas(); }, this);\n"
             "    }\n", "create")
    s = once(s, "        if (resuelta && REXCVAR_GET(nfsmw_nativo_diag_resueltas) &&\n            resueltas_fotograma_.size() < 64 &&\n",
             "        if (resuelta && gsr2_ && resoluciones_fotograma_.size() < kResolucionesFotogramaMax) {\n"
             "          // carbon-gsr2: which resolve is the scene, which the composited scene before the HUD, and their depth.\n"
             "          ResolucionFotograma r;\n"
             "          r.destino = base & 0x1FFFFFFF;\n"
             "          r.origen = (uint64_t(info_color & 0xFFF) << 20) | (uint64_t(formato_color) << 16) | pitch;\n"
             "          r.pitch = pitch;\n"
             "          r.info_profundidad = reg.rb_depth_info;\n"
             "          r.x0 = x0;\n          r.y0 = y0;\n          r.x1 = x1;\n          r.y1 = y1;\n"
             "          r.ancho = resuelta->imagen.ancho;\n"
             "          r.alto = resuelta->imagen.alto;\n"
             "          r.intercambio_rb = resuelta->intercambio_rb;\n"
             "          resoluciones_fotograma_.push_back(r);\n"
             "        }\n"
             "        if (resuelta && REXCVAR_GET(nfsmw_nativo_diag_resueltas) &&\n            resueltas_fotograma_.size() < 64 &&\n",
             "copiar record")
    s = once(s, "    Imagen* const origen_frontal = FrontalAlPresentar(base, ancho, alto);\n",
             "    Imagen* const origen_frontal = FrontalAlPresentar(base, ancho, alto);\n"
             "    // carbon-gsr2: what the upscaler needs from this frame's resolves (before forgetting them).\n"
             "    PlanGsr2 plan_gsr2;\n"
             "    PrepararGsr2(presentador, base, origen_frontal, plan_gsr2);\n"
             "    GsrFinDeFotograma();\n"
             "    resoluciones_fotograma_.clear();\n", "presentar plan")
    s = once(s,
             "    presentador->RefreshGuestOutput(\n"
             "        w, h, 1280, 720, [&](rex::ui::Presenter::GuestOutputRefreshContext& base_contexto) {\n"
             "          entrada_llamada = std::chrono::steady_clock::now();\n"
             "          llamada = true;\n"
             "          auto& contexto =\n"
             "              static_cast<VulkanPresenter::VulkanGuestOutputRefreshContext&>(base_contexto);\n"
             "          pintado = PintarSalida(contexto, origen_frontal ? *origen_frontal : resuelta.imagen, w, h,\n"
             "                                 origen_frontal != nullptr);  // nfsmw_nativo_frontal_perezoso\n"
             "          salida_llamada = std::chrono::steady_clock::now();\n"
             "          return pintado;\n"
             "        });\n",
             "    // carbon-gsr2: the display proportion is the front buffer's own when it is wider than 16:9 (widescreen).\n"
             "    const bool mas_ancha = uint64_t(w) * 9 > uint64_t(h) * 16 + h;\n"
             "    // The presenter's image gets the screen's size and GSR 2 fills it, if the frame is smaller: the largest\n"
             "    // rectangle of the display proportion inside the screen.\n"
             "    if (plan_gsr2.activo) {\n"
             "      const uint64_t px = mas_ancha ? w : 1280, py = mas_ancha ? h : 720;\n"
             "      if (uint64_t(plan_gsr2.ancho_salida) * py > uint64_t(plan_gsr2.alto_salida) * px) {\n"
             "        plan_gsr2.ancho_salida = uint32_t(uint64_t(plan_gsr2.alto_salida) * px / py);\n"
             "      } else {\n"
             "        plan_gsr2.alto_salida = uint32_t(uint64_t(plan_gsr2.ancho_salida) * py / px);\n"
             "      }\n"
             "    }\n"
             "    const bool con_gsr2 = plan_gsr2.activo && (plan_gsr2.ancho_salida > w || plan_gsr2.alto_salida > h);\n"
             "    presentador->RefreshGuestOutput(\n"
             "        con_gsr2 ? plan_gsr2.ancho_salida : w, con_gsr2 ? plan_gsr2.alto_salida : h, mas_ancha ? w : 1280,\n"
             "        mas_ancha ? h : 720, [&](rex::ui::Presenter::GuestOutputRefreshContext& base_contexto) {\n"
             "          entrada_llamada = std::chrono::steady_clock::now();\n"
             "          llamada = true;\n"
             "          auto& contexto =\n"
             "              static_cast<VulkanPresenter::VulkanGuestOutputRefreshContext&>(base_contexto);\n"
             "          pintado = PintarSalida(contexto, origen_frontal ? *origen_frontal : resuelta.imagen, w, h,\n"
             "                                 origen_frontal != nullptr,  // nfsmw_nativo_frontal_perezoso\n"
             "                                 con_gsr2 ? &plan_gsr2 : nullptr);\n"
             "          salida_llamada = std::chrono::steady_clock::now();\n"
             "          return pintado;\n"
             "        });\n"
             "    if (gsr2_) {\n"
             "      nfsmw::gsr2::AnotarUso(con_gsr2 && llamada && ultimo_gsr2_hecho_);  // the game jitters only while it upscales\n"
             "    }\n", "presentar refresh")
    # PrepararGsr2, before PintarSalida's comment
    prep = open(os.path.dirname(os.path.abspath(__file__)) + "/prepararGsr2.inc").read() if False else None
    s = once(s, "  // desde_destino = the source is a render target's image (or a retained one) with the front buffer in its\n",
             "@@PREPARAR@@  // desde_destino = the source is a render target's image (or a retained one) with the front buffer in its\n", "prep anchor")
    s = s.replace("@@PREPARAR@@", r'''  // carbon-gsr2: the composited scene before the HUD, copied when the draws to the front render target change from
  // "scene" (depth tested, or opaque) to "HUD" (depth off and blended: FEng text, icons, the rain). GSR 2 compares the
  // final frame with this copy to find the HUD pixels: those are not 3D (no jitter, no history). The copy goes to a
  // texture with a made-up address, in the same format as the image GSR 2 reads, so both match bit for bit.
  static constexpr uint32_t kClaveInstantaneaGsr = 0x3FFF0000u;  // outside the 512 MB of guest memory

  bool GsrEsElDestinoFrontal(uint32_t base_rt, uint32_t pitch) const {
    return gsr_rt_ != 0 && base_rt == uint32_t((gsr_rt_ >> 20) & 0xFFF) && pitch == uint32_t(gsr_rt_ & 0xFFFF);
  }

  bool GsrInstantanea(Imagen& rt) {
    if (gsr_snaps_ >= 12 || gsr_formato_ == VK_FORMAT_UNDEFINED || !dibujos_ || !Grabar()) {
      return false;
    }
    const bool igual = rt.formato == gsr_formato_;
    if (igual ? !copiar_imagen_ : !blit_) {
      return false;
    }
    dibujos_->TerminarPase();  // a copy is not allowed inside a pass (the next draw resumes it)
    Resuelta* s = ObtenerResuelta(kClaveInstantaneaGsr, gsr_ancho_, gsr_alto_, 0, false, gsr_formato_);
    if (!s) {
      return false;
    }
    Preparar(rt);
    Preparar(s->imagen);
    // The render target may be lent out (its content is in the texture it was resolved to, after a resolve by
    // swapping): bring it back before reading it, as the next draw would.
    if (rt.contenido_invalido) {
      ++gsr_restauradas_;
      RestaurarContenido(rt, true);
    }
    const int64_t x0 = std::max<int32_t>(gsr_rect_[0], 0), y0 = std::max<int32_t>(gsr_rect_[1], 0);
    const int64_t dx = gsr_dx_, dy = gsr_dy_;
    const int64_t ancho = std::min<int64_t>({int64_t(gsr_rect_[2]) - x0, int64_t(rt.ancho) - x0, int64_t(s->imagen.ancho) - dx});
    const int64_t alto = std::min<int64_t>({int64_t(gsr_rect_[3]) - y0, int64_t(rt.alto) - y0, int64_t(s->imagen.alto) - dy});
    if (ancho <= 0 || alto <= 0) {
      return false;
    }
    MarcarGpu(kGpuCopias);
    if (igual) {
      VkImageCopy copia{};
      copia.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
      copia.srcOffset = {int32_t(x0), int32_t(y0), 0};
      copia.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
      copia.dstOffset = {int32_t(dx), int32_t(dy), 0};
      copia.extent = {uint32_t(ancho), uint32_t(alto), 1};
      copiar_imagen_(comandos_trabajo_, rt.imagen, VK_IMAGE_LAYOUT_GENERAL, s->imagen.imagen, VK_IMAGE_LAYOUT_GENERAL, 1,
                     &copia);
    } else {
      VkImageBlit conversion{};  // a half float render target to an 8-bit texture (as Copiar does)
      conversion.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
      conversion.srcOffsets[0] = {int32_t(x0), int32_t(y0), 0};
      conversion.srcOffsets[1] = {int32_t(x0 + ancho), int32_t(y0 + alto), 1};
      conversion.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
      conversion.dstOffsets[0] = {int32_t(dx), int32_t(dy), 0};
      conversion.dstOffsets[1] = {int32_t(dx + ancho), int32_t(dy + alto), 1};
      blit_(comandos_trabajo_, rt.imagen, VK_IMAGE_LAYOUT_GENERAL, s->imagen.imagen, VK_IMAGE_LAYOUT_GENERAL, 1,
            &conversion, VK_FILTER_NEAREST);
    }
    ++gsr_snaps_;
    gsr_snap_valida_ = true;
    GsrAnotarTramo('C', 0);
    return true;
  }

  // The run-length list of draw classes of the frame, for the log: S = depth tested, O = opaque without depth,
  // H = blended without depth.
  void GsrAnotarTramo(char clase, uint32_t huella, uint32_t huella_vs = 0) {
    if (clase == gsr_clase_tramo_ && huella == gsr_huella_tramo_ && huella_vs == gsr_huella_vs_tramo_) {
      ++gsr_cuenta_tramo_;
      return;
    }
    if (gsr_clase_tramo_ && gsr_secuencia_.size() < 1200) {
      gsr_secuencia_ += fmt::format(" {}{}", gsr_clase_tramo_, gsr_cuenta_tramo_);
      if (gsr_clase_tramo_ == 'O' || gsr_clase_tramo_ == 'H') {
        gsr_secuencia_ += fmt::format("({:08X}/{:08X})", gsr_huella_tramo_, gsr_huella_vs_tramo_);
      }
    }
    gsr_clase_tramo_ = clase;
    gsr_cuenta_tramo_ = 1;
    gsr_huella_tramo_ = huella;
    gsr_huella_vs_tramo_ = huella_vs;
  }

  void GsrAntesDeDibujo(const PeticionDibujo& p) {
    const uint32_t* r = p.registros;
    if (!r || !dibujos_) {
      return;
    }
    if ((r[gr::XE_GPU_REG_RB_MODECONTROL] & 0x7) != uint32_t(xenos::EdramMode::kColorDepth)) {
      return;
    }
    const uint32_t info = r[gr::XE_GPU_REG_RB_COLOR_INFO];
    const uint32_t pitch = r[gr::XE_GPU_REG_RB_SURFACE_INFO] & 0x3FFF;
    if (!GsrEsElDestinoFrontal(info & 0xFFF, pitch) || (r[gr::XE_GPU_REG_RB_COLOR_MASK] & 0xF) == 0) {
      return;
    }
    const uint32_t control_z = r[gr::XE_GPU_REG_RB_DEPTHCONTROL];
    const uint32_t mezcla = r[gr::XE_GPU_REG_RB_BLENDCONTROL0];
    const bool con_z = ((control_z >> 1) & 0x1) != 0;
    const bool opaco = (mezcla & 0x1F) == 1 && ((mezcla >> 8) & 0x1F) == 0;  // ONE, ZERO
    const bool hud = !con_z && !opaco;
    const uint32_t huella = p.ps ? uint32_t(p.ps->huella) : 0;
    GsrAnotarTramo(con_z ? 'S' : (opaco ? 'O' : 'H'), con_z ? 0 : huella, con_z || !p.vs ? 0 : uint32_t(p.vs->huella));
    if (!hud) {
      gsr_vio_escena_ = true;
      gsr_sucio_ = gsr_necesita_copia_;  // the render target has scene draws that the last copy does not have
      ++gsr_n_escena_;
      return;
    }
    ++gsr_n_hud_;
    if (gsr_sucio_) {  // the first HUD draw after scene draws: the copy of the scene before the HUD
      ++gsr_cortes_;
      Imagen* rt = ObtenerDestino(info & 0xFFF, (info >> 16) & 0xF, pitch);
      if (rt && GsrInstantanea(*rt)) {
        gsr_sucio_ = false;
      } else {
        ++gsr_saltadas_;
        GsrAnotarTramo('x', 0);
      }
    }
  }

  // A resolve of the render target (the front buffer's, or any other of the frame): if scene draws came after the
  // last copy, the HUD is empty this frame (or nothing came after them): the copy is the frame itself.
  void GsrAntesDeResolver(Imagen& rt, uint32_t base_rt, uint32_t pitch) {
    if (!GsrEsElDestinoFrontal(base_rt, pitch)) {
      return;
    }
    GsrAnotarTramo('R', 0);
    if (gsr_sucio_ && GsrInstantanea(rt)) {
      gsr_sucio_ = false;
    }
  }

  void GsrFinDeFotograma() {
    if (gsr_rt_ == 0) {
      return;
    }
    ++gsr_fotogramas_;
    static int fallos_anotados = 0;
    if (gsr_fotogramas_ <= 6 || gsr_fotogramas_ % 300 == 0 || (gsr_necesita_copia_ && !gsr_snap_valida_ && fallos_anotados++ < 20)) {
      GsrAnotarTramo(0, 0);  // closes the last run
      REXLOG_INFO("[gsr2] dibujos al RT frontal (fotograma {}): {} de escena (S con profundidad, O opacos), {} de HUD (H sin "
                  "profundidad y con mezcla), {} cortes, {} copias de la escena previa al HUD ({}), {} saltadas, {} destinos restaurados antes de copiar; "
                  "secuencia (S/O/H dibujos, R resuelto del RT, C copia hecha, x copia fallida):{}",
                  gsr_fotogramas_, gsr_n_escena_, gsr_n_hud_, gsr_cortes_, gsr_snaps_, gsr_snap_valida_ ? "valida" : "NINGUNA",
                  gsr_saltadas_, gsr_restauradas_, gsr_secuencia_);
    }
    gsr_vio_escena_ = gsr_sucio_ = gsr_snap_valida_ = false;
    gsr_snaps_ = gsr_n_escena_ = gsr_n_hud_ = gsr_cortes_ = gsr_saltadas_ = gsr_restauradas_ = 0;
    gsr_clase_tramo_ = 0;
    gsr_cuenta_tramo_ = 0;
    gsr_huella_tramo_ = gsr_huella_vs_tramo_ = 0;
    gsr_secuencia_.clear();
  }

  // carbon-gsr2: the frame's resolves -> what GSR 2 needs (plan.activo = false if something is missing).
  void PrepararGsr2(rex::ui::Presenter* presentador, uint32_t base, Imagen* origen_frontal, PlanGsr2& plan) {
    plan = PlanGsr2{};
    const bool desde_destino = origen_frontal != nullptr;
    if (!gsr2_ || !presentador || resoluciones_fotograma_.empty()) {
      return;
    }
    presentador->GetPaintSurfaceSize(plan.ancho_salida, plan.alto_salida);
    if (!plan.ancho_salida || !plan.alto_salida) {
      return;
    }
    // The resolve that made the front buffer (the last one to that address).
    size_t f = resoluciones_fotograma_.size();
    for (size_t i = resoluciones_fotograma_.size(); i-- > 0;) {
      if (resoluciones_fotograma_[i].destino == base) {
        f = i;
        break;
      }
    }
    if (f == resoluciones_fotograma_.size()) {
      if (avisos_gsr2_ < 3) {
        ++avisos_gsr2_;
        REXLOG_INFO("[gsr2] ningun resuelto del fotograma va al buffer frontal {:08X} ({} resueltos): se presenta como siempre",
                    base, resoluciones_fotograma_.size());
      }
      return;
    }
    const ResolucionFotograma& frontal = resoluciones_fotograma_[f];
    // What the copy of the scene before the HUD must look like (next frame): the same image GSR 2 reads as color.
    const Imagen* imagen_color = origen_frontal;
    if (!imagen_color) {
      const auto itc = resueltas_.find(base);
      imagen_color = itc != resueltas_.end() ? &itc->second.imagen : nullptr;
    }
    if (imagen_color && imagen_color->formato != VK_FORMAT_UNDEFINED) {
      gsr_rt_ = frontal.origen;
      gsr_formato_ = imagen_color->formato;
      gsr_ancho_ = imagen_color->ancho;
      gsr_alto_ = imagen_color->alto;
      gsr_dx_ = desde_destino ? frontal.x0 : 0;
      gsr_dy_ = desde_destino ? frontal.y0 : 0;
      gsr_rect_[0] = frontal.x0;
      gsr_rect_[1] = frontal.y0;
      gsr_rect_[2] = frontal.x1;
      gsr_rect_[3] = frontal.y1;
    }
    // The depth bound when that render target was resolved for the first time this frame (the scene).
    uint32_t info_profundidad = frontal.info_profundidad;
    for (size_t i = 0; i <= f; ++i) {
      if (resoluciones_fotograma_[i].origen == frontal.origen) {
        info_profundidad = resoluciones_fotograma_[i].info_profundidad;
        break;
      }
    }
    const uint64_t clave_profundidad = (uint64_t(info_profundidad & 0xFFF) << 20) |
                                       (uint64_t((info_profundidad >> 16) & 0x1) << 16) | frontal.pitch;
    const auto it_profundidad = profundidades_.find(clave_profundidad);
    if (it_profundidad == profundidades_.end() || !it_profundidad->second.preparada ||
        it_profundidad->second.contenido_invalido) {
      if (!avisado_gsr2_sin_profundidad_) {
        avisado_gsr2_sin_profundidad_ = true;
        REXLOG_INFO("[gsr2] sin destino de profundidad para la escena (RB_DEPTH_INFO {:08X}, pitch {}): ese "
                    "fotograma se presenta como siempre",
                    info_profundidad, frontal.pitch);
      }
      return;
    }
    const Imagen& profundidad = it_profundidad->second;
    nfsmw::gsr2::EntradasVulkan& e = plan.entradas;
    e.profundidad = profundidad.imagen;
    e.formato_profundidad = profundidad.formato;
    e.profundidad_ancho = profundidad.ancho;
    e.profundidad_alto = profundidad.alto;
    e.rect_profundidad[0] = float(frontal.x0);
    e.rect_profundidad[1] = float(frontal.y0);
    e.rect_profundidad[2] = float(frontal.x1);
    e.rect_profundidad[3] = float(frontal.y1);
    // A frame with HUD draws only (a 2D menu page) has no 3D to accumulate: it is upscaled without history.
    e.solo_2d = !gsr_vio_escena_ && gsr_n_hud_ > 0;
    // The composited scene before the HUD, as Most Wanted does it: the last earlier resolve of the same render target
    // (same EDRAM base and pitch; Carbon names it with another format, 30780 vs C0780), the same size, to another
    // texture. If the game made none, our own copy (GsrInstantanea, enabled from the next frame on).
    bool con_escena = false;
    bool escena_laxa = false;  // true: our own copy
    const uint64_t clave_rt = frontal.origen & ~(uint64_t(0xF) << 16);
    for (size_t i = f; i-- > 0;) {
      const ResolucionFotograma& r = resoluciones_fotograma_[i];
      if ((r.origen & ~(uint64_t(0xF) << 16)) != clave_rt || r.destino == base || r.ancho != frontal.ancho ||
          r.alto != frontal.alto) {
        continue;
      }
      const auto it = resueltas_.find(r.destino);
      if (it != resueltas_.end() && it->second.imagen.preparada && it->second.imagen.ancho == frontal.ancho &&
          it->second.imagen.alto == frontal.alto) {
        e.escena = it->second.imagen.vista;
        e.escena_rb = it->second.intercambio_rb != (desde_destino ? false : frontal.intercambio_rb);
        con_escena = true;
        gsr_necesita_copia_ = false;  // the game's own copy exists: no copy of ours
      }
      break;
    }
    if (!con_escena && imagen_color) {
      gsr_necesita_copia_ = true;
      if (gsr_snap_valida_) {
        const auto its = resueltas_.find(kClaveInstantaneaGsr);
        if (its != resueltas_.end() && its->second.imagen.preparada && its->second.imagen.ancho == imagen_color->ancho &&
            its->second.imagen.alto == imagen_color->alto && its->second.imagen.formato == imagen_color->formato) {
          e.escena = its->second.imagen.vista;
          // the render target's data in its own order; the color is the front resolve's
          e.escena_rb = desde_destino ? false : frontal.intercambio_rb;
          con_escena = true;
          escena_laxa = true;
        }
      }
    }
    if (avisos_gsr2_ < 3) {  // what was found, for the first frames (to tune it on the device)
      ++avisos_gsr2_;
      std::string lista;
      for (size_t i = 0; i < resoluciones_fotograma_.size() && i < 16; ++i) {
        const ResolucionFotograma& r = resoluciones_fotograma_[i];
        lista += fmt::format(" [{:08X} RT {:X} {}x{}{}]", r.destino, r.origen, r.ancho, r.alto, i == f ? " FRONTAL" : "");
      }
      REXLOG_INFO("[gsr2] resueltos del fotograma:{}", lista);
      REXLOG_INFO("[gsr2] fotograma: buffer frontal {:08X} {}x{} (RT {:X}), profundidad {:08X} {}x{} pitch {}, rect "
                  "({},{})-({},{}), {} resueltos, escena previa al HUD: {}, salida {}x{}",
                  base, frontal.ancho, frontal.alto, frontal.origen, info_profundidad, profundidad.ancho,
                  profundidad.alto, frontal.pitch, frontal.x0, frontal.y0, frontal.x1, frontal.y1,
                  resoluciones_fotograma_.size(), con_escena ? (escena_laxa ? "si (copia propia)" : "si (resuelto)") : "no",
                  plan.ancho_salida, plan.alto_salida);
    }
    plan.activo = true;
  }

''')
    # PintarSalida
    s = once(s, "  bool PintarSalida(VulkanPresenter::VulkanGuestOutputRefreshContext& contexto, Imagen& origen,\n"
                "                    uint32_t ancho, uint32_t alto, bool desde_destino = false) {\n",
             "  bool PintarSalida(VulkanPresenter::VulkanGuestOutputRefreshContext& contexto, Imagen& origen,\n"
             "                    uint32_t ancho, uint32_t alto, bool desde_destino = false, PlanGsr2* plan = nullptr) {\n"
             "    // carbon-gsr2: with a plan, the output (the presenter's image) has the screen's size.\n"
             "    const uint32_t ancho_salida = plan ? plan->ancho_salida : ancho;\n"
             "    const uint32_t alto_salida = plan ? plan->alto_salida : alto;\n", "pintar sig")
    s = once(s, "      info.width = ancho;\n      info.height = alto;\n      info.layers = 1;\n",
             "      info.width = ancho_salida;\n      info.height = alto_salida;\n      info.layers = 1;\n", "fb size")
    s = once(s,
             "    VkDescriptorImageInfo info_imagen{};\n"
             "    info_imagen.imageView = origen.vista;\n"
             "    info_imagen.imageLayout = VK_IMAGE_LAYOUT_GENERAL;\n"
             "    VkWriteDescriptorSet escritura{};\n"
             "    escritura.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;\n"
             "    escritura.dstSet = descriptores_salida_[s];\n"
             "    escritura.dstBinding = 0;\n"
             "    escritura.descriptorCount = 1;\n"
             "    escritura.descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;\n"
             "    escritura.pImageInfo = &info_imagen;\n"
             "    dfn_.vkUpdateDescriptorSets(device_, 1, &escritura, 0, nullptr);\n\n"
             "    dfn_.vkResetCommandPool(device_, pools_salida_[s], 0);\n",
             "    dfn_.vkResetCommandPool(device_, pools_salida_[s], 0);\n", "descriptor block")
    s = once(s, "    pase.renderArea.extent = {ancho, alto};\n", "    pase.renderArea.extent = {ancho_salida, alto_salida};\n", "render area")
    s = once(s,
             "    dfn_.vkCmdBeginRenderPass(comandos_salida_[s], &pase, VK_SUBPASS_CONTENTS_INLINE);\n"
             "    const VkViewport viewport{0.0f, 0.0f, float(ancho), float(alto), 0.0f, 1.0f};\n"
             "    dfn_.vkCmdSetViewport(comandos_salida_[s], 0, 1, &viewport);\n"
             "    const VkRect2D tijera{{0, 0}, {ancho, alto}};\n",
             "    // carbon-gsr2: both passes before the output pass, which then reads the upscaled image 1 to 1.\n"
             "    VkImageView vista_fuente = origen.vista;\n"
             "    uint32_t fuente_ancho = origen.ancho, fuente_alto = origen.alto;\n"
             "    bool gsr2_hecho = false;\n"
             "    if (plan && gsr2_) {\n"
             "      plan->entradas.color = origen.vista;\n"
             "      plan->entradas.ancho = ancho;\n"
             "      plan->entradas.alto = alto;\n"
             "      const VkImageView escalada = gsr2_->Grabar(comandos_salida_[s], s, plan->entradas, ancho_salida, alto_salida,\n"
             "                                                 nfsmw::gsr2::CamaraDelSwap());\n"
             "      if (escalada != VK_NULL_HANDLE) {\n"
             "        vista_fuente = escalada;\n"
             "        fuente_ancho = ancho_salida;\n"
             "        fuente_alto = alto_salida;\n"
             "        gsr2_hecho = true;\n"
             "      }\n"
             "    }\n"
             "    ultimo_gsr2_hecho_ = gsr2_hecho;\n"
             "    VkDescriptorImageInfo info_imagen{};\n"
             "    info_imagen.imageView = vista_fuente;\n"
             "    info_imagen.imageLayout = VK_IMAGE_LAYOUT_GENERAL;\n"
             "    VkWriteDescriptorSet escritura{};\n"
             "    escritura.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;\n"
             "    escritura.dstSet = descriptores_salida_[s];\n"
             "    escritura.dstBinding = 0;\n"
             "    escritura.descriptorCount = 1;\n"
             "    escritura.descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;\n"
             "    escritura.pImageInfo = &info_imagen;\n"
             "    dfn_.vkUpdateDescriptorSets(device_, 1, &escritura, 0, nullptr);\n\n"
             "    dfn_.vkCmdBeginRenderPass(comandos_salida_[s], &pase, VK_SUBPASS_CONTENTS_INLINE);\n"
             "    const VkViewport viewport{0.0f, 0.0f, float(ancho_salida), float(alto_salida), 0.0f, 1.0f};\n"
             "    dfn_.vkCmdSetViewport(comandos_salida_[s], 0, 1, &viewport);\n"
             "    const VkRect2D tijera{{0, 0}, {ancho_salida, alto_salida}};\n", "gsr block")
    s = once(s,
             "      const bool exacta = desde_destino || (ancho == origen.ancho && alto == origen.alto);\n"
             "      const bool fxaa = !desde_destino && nfsmw::ajustes::AntialiasingFxaa();\n",
             "      // With GSR 2 the upscaled image has the output's size and is already antialiased (no FXAA). With a GSR 2\n"
             "      // plan that could not run, the output is larger than the frame: bilinear.\n"
             "      const bool exacta = gsr2_hecho || (desde_destino && !plan) ||\n"
             "                          (ancho_salida == fuente_ancho && alto_salida == fuente_alto);\n"
             "      const bool fxaa = !desde_destino && !gsr2_hecho && nfsmw::ajustes::AntialiasingFxaa();\n", "exacta")
    s = once(s,
             '        REXLOG_INFO("[nativo] C2: salida de {}x{} desde un origen de {}x{}: rampa con muestreo bilineal", ancho,\n'
             "                    alto, origen.ancho, origen.alto);\n",
             '        REXLOG_INFO("[nativo] C2: salida de {}x{} desde un origen de {}x{}: rampa con muestreo bilineal",\n'
             "                    ancho_salida, alto_salida, fuente_ancho, fuente_alto);\n", "bilinear log")
    s = once(s, "    } bilineal = {{0, 0}, {1.0f / float(ancho), 1.0f / float(alto)}};\n",
             "    } bilineal = {{0, 0}, {1.0f / float(ancho_salida), 1.0f / float(alto_salida)}};\n", "bilineal")
    s = once(s, "    if (desde_destino) {\n      // And nothing submitted later (the next frame draws and clears that image again) writes it before the\n",
             "    if (gsr2_hecho) {\n"
             "      // The next frame's work writes again what GSR 2 read (color, depth, the copy) and the next output the\n"
             "      // other history image: after this one has read them.\n"
             "      dfn_.vkCmdPipelineBarrier(comandos_salida_[s], VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT,\n"
             "                                VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 0, nullptr);\n"
             "    } else if (desde_destino) {\n"
             "      // And nothing submitted later (the next frame draws and clears that image again) writes it before the\n", "post barrier")
    s = once(s, "  VkSampler sampler_ = VK_NULL_HANDLE;\n",
             "  VkSampler sampler_ = VK_NULL_HANDLE;\n"
             "  // carbon-gsr2: the upscaler (only with the cvar) and this frame's resolves (Copiar -> Presentar).\n"
             "  std::unique_ptr<nfsmw::gsr2::Gsr2Vulkan> gsr2_;\n"
             "  std::vector<ResolucionFotograma> resoluciones_fotograma_;\n"
             "  bool avisado_gsr2_sin_profundidad_ = false;\n"
             "  bool ultimo_gsr2_hecho_ = false;  // PintarSalida -> Presentar\n"
             "  int avisos_gsr2_ = 0;\n"
             "  // carbon-gsr2: the scene before the HUD (GsrAntesDeDibujo). What the next frame's copy must look like comes\n"
             "  // from the previous frame's plan (PrepararGsr2).\n"
             "  uint64_t gsr_rt_ = 0;  // front render target key (as ResolucionFotograma::origen); 0 = not known yet\n"
             "  VkFormat gsr_formato_ = VK_FORMAT_UNDEFINED;\n"
             "  uint32_t gsr_ancho_ = 0, gsr_alto_ = 0;\n"
             "  int32_t gsr_dx_ = 0, gsr_dy_ = 0;\n"
             "  int32_t gsr_rect_[4] = {};\n"
             "  bool gsr_vio_escena_ = false, gsr_sucio_ = false, gsr_snap_valida_ = false, gsr_necesita_copia_ = false;\n"
             "  uint32_t gsr_snaps_ = 0, gsr_n_escena_ = 0, gsr_n_hud_ = 0, gsr_cortes_ = 0, gsr_saltadas_ = 0;\n"
             "  uint32_t gsr_restauradas_ = 0;\n"
             "  uint32_t gsr_cuenta_tramo_ = 0;\n"
             "  char gsr_clase_tramo_ = 0;\n"
             "  uint32_t gsr_huella_tramo_ = 0, gsr_huella_vs_tramo_ = 0;\n"
             "  std::string gsr_secuencia_;\n"
             "  uint32_t gsr_fotogramas_ = 0;\n", "members")
    wr(p, s)
    print("patched nfsmw_nativo_destinos.cpp")

# ---------------------------------------------------------------- 4b. HUD layer at the output's resolution
# carbon-gsr2 capa: the HUD (and menus) is drawn at the output's size: its draws go to a transparent layer of the
# output's size (premultiplied color + coverage) through the renderer's own scaled-pass code, and the layer is put
# over the upscaled scene when presenting. GSR 2 then only upscales the scene. Separate blocks per file because the
# gsr2 sources and the shader header stay on the runner (untracked) from earlier runs.
import base64, zlib
COMPONER_B64 = (
    "eNqVWNtu40YMffdX6LEF0s0MORepxT7YstT+QJ+KReC6znaBjR3Y3ktR9N87smOJnJD2JIAWsxbJwzs5ur+vft1sN/vVcfNX9bjf"
    "PVXfDvcfD3u4X++ennfpzbvH/epj9cN6tf9zt/1pePVz9dvvy+rz6p/Nvtp9Tf8c/95UX54P69XnJOSwTvJ+fDebrXfbw7H68ml7"
    "RHg4VtvHw9O3h8Mg4OEi++H58MeH6n3176xKf+a7iYAGDN4NZ2NseszLuU7P4uWc/pydziMNJBb6++UcTrwXDPLOtR5d6+JwDi66"
    "iNANZzSYXpzPGQamR/r9LHPCiOnpyTuXn0MXmmDDUpFFfh/1wMElmR1UbiQ6IvkdxrNtL2eXHq/qxDGo7ZSnmc7REF/73A4XfB/a"
    "cNLPYYjBRrhgJL9D6EMv+CHT0Z5sSrwm6YgF9GHEOPE4icdnPPPhHDH46M+xSVg+Qnzx80lXx/CYr+DsRx9wkHGRm2R0so7gJ3qn"
    "03OM07toUr56N/pt+N/E46KcS7SGxvzEEz3DsCjnPpWb/CvGQKMBm+UVFPBAgR6R0UwYudw50+V1DV2jBwUj0wXsbX3BFdB4pQbd"
    "KzoZ2xbQg17njCcU6LtQaXjutgWyutt5RWlsV2hHfxsbTZkdWBBnjAU0TVle4bxA1qKApi3zFS4LZHWFvirwuzPKPJfmGAq9RKJL"
    "OWPpLKJ9xci1wnpJZgflpxhMVi3M42w2s745z+rDKLosGI/Yu5gerbKXUFkuy5lWmRmafzrdDs0/FhT/XPRoEg2pCeuuYFhldzLq"
    "fib2Faaf1nepLpnfrL8xE4HPElvzGcXwG1l3WyvYjTyv8l5iKU8r28R6OLHDKruZzXs7KDmKsq8B5VwAYLbyvcTLs0yLJyzv5B6x"
    "0DFgqcwiVHxFbMWT7tjXua+yvEJUepGRMSg9OtW3HMMrtTYvsKOWd2UMSp3ndxEj6JjqoKdyvdKH6gyjEezI6wDu5N1VoU+5J+zt"
    "As+t3Zn2ynTncz3rjzx3jcLf3+hXSY/QybG0VsHAbD43jEe0j/ZaG6V7lMBD4sl6zHzKGR+U3rNkeNyOhRKDyPa+1/YNvnKyTXl9"
    "WBI338txpjs169OdeL8eeiXruzQGNC+hIAZ07wbP6LkdJAYQ3xYDqBW8qMec9ermjTGYM2z2vUSNwULhb9QYjN+MXK/PKHoXgcWN"
    "u0y+PwCrM7WXjBhXegm9l4w5UvNekt/V6D2F8kP/Bt0znV5hWOHO6vm3NzpjMMi5jk7PXTZzoiCrzvbSuXJ3six+3I4ozzWEyaYa"
    "FYy5QH/GnjAG/k7+VkBnDvUnktqsrcLb6jEf5Q61bRXdl0yWOM+9vRKPTuG3Bdj9lTsnkL5r5Jqg90FmR6dggN536Q43yk3flvvl"
    "dE55Mfvvl9n/SdzKvg=="
)
hdr_c = APP + "/shaders/nfsmw_sgsr2_componer_ps.h"
cc = zlib.decompress(base64.b64decode(COMPONER_B64)).decode()
if not os.path.exists(hdr_c) or rd(hdr_c) != cc:
    wr(hdr_c, cc)
    print("gsr2 composition shader written")

h = APP + "/nfsmw_gsr2.h"
sh = rd(h)
if "carbon-gsr2 capa" not in sh:
    sh = once(sh, "  bool solo_2d = false;    // carbon-gsr2: no 3D draw this frame (menus): no history, just the upscale\n",
              "  bool solo_2d = false;    // carbon-gsr2: no 3D draw this frame (menus): no history, just the upscale\n"
              "  // carbon-gsr2 capa: the HUD layer (premultiplied color + coverage, output size, GENERAL) or VK_NULL_HANDLE\n"
              "  VkImageView capa = VK_NULL_HANDLE;\n", "capa field")
    wr(h, sh)
    print("gsr2 header: HUD layer field")

g = APP + "/nfsmw_gsr2.cpp"
s = rd(g)
if "carbon-gsr2 capa" not in s:
    s = once(s, '#include "shaders/nfsmw_sgsr2_escalar_ps.h"\n',
             '#include "shaders/nfsmw_sgsr2_escalar_ps.h"\n#include "shaders/nfsmw_sgsr2_componer_ps.h"  // carbon-gsr2 capa\n', "capa include")
    s = once(s, "    for (VkPipeline p : {pipeline_convertir_, pipeline_escalar_}) {",
             "    for (VkPipeline p : {pipeline_convertir_, pipeline_escalar_, pipeline_componer_}) {", "capa dtor pipeline")
    s = once(s, "    for (VkShaderModule m : {fs_convertir_, fs_escalar_}) {",
             "    for (VkShaderModule m : {fs_convertir_, fs_escalar_, fs_componer_}) {", "capa dtor shader")
    s = once(s, "    const uint32_t conjuntos = ranuras_ * 2;\n", "    const uint32_t conjuntos = ranuras_ * 3;  // carbon-gsr2 capa: convert, upscale, HUD layer\n", "capa sets")
    s = once(s, "      r.conjunto_escalar = sets[1];\n",
             "      r.conjunto_escalar = sets[1];\n"
             "      {  // carbon-gsr2 capa: the third set (the HUD layer over the upscaled image)\n"
             "        VkDescriptorSetAllocateInfo reserva3{};\n"
             "        reserva3.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;\n"
             "        reserva3.descriptorPool = pool_;\n"
             "        reserva3.descriptorSetCount = 1;\n"
             "        reserva3.pSetLayouts = &layout_conjunto_;\n"
             "        if (dfn_.vkAllocateDescriptorSets(device_, &reserva3, &r.conjunto_componer) != VK_SUCCESS) {\n"
             "          return false;\n"
             "        }\n"
             "        VkDescriptorImageInfo muestreador3{cercano_, VK_NULL_HANDLE, VK_IMAGE_LAYOUT_UNDEFINED};\n"
             "        VkWriteDescriptorSet escritura3{};\n"
             "        escritura3.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;\n"
             "        escritura3.dstSet = r.conjunto_componer;\n"
             "        escritura3.dstBinding = 4;\n"
             "        escritura3.descriptorCount = 1;\n"
             "        escritura3.descriptorType = VK_DESCRIPTOR_TYPE_SAMPLER;\n"
             "        escritura3.pImageInfo = &muestreador3;\n"
             "        dfn_.vkUpdateDescriptorSets(device_, 1, &escritura3, 0, nullptr);\n"
             "      }\n", "capa third set")
    s = once(s, "    if (fs_convertir_ == VK_NULL_HANDLE || fs_escalar_ == VK_NULL_HANDLE) {\n      return false;\n    }\n",
             "    if (fs_convertir_ == VK_NULL_HANDLE || fs_escalar_ == VK_NULL_HANDLE) {\n      return false;\n    }\n"
             "    fs_componer_ = rex::ui::vulkan::util::CreateShaderModule(dispositivo_, shaders::nfsmw_sgsr2_componer_ps,\n"
             "                                                             sizeof(shaders::nfsmw_sgsr2_componer_ps));  // carbon-gsr2 capa\n",
             "capa shader module")
    s = once(s, "    pipeline_escalar_ = CrearPipeline(fs_escalar_);\n",
             "    pipeline_escalar_ = CrearPipeline(fs_escalar_);\n"
             "    pipeline_componer_ = fs_componer_ != VK_NULL_HANDLE ? CrearPipeline(fs_componer_) : VK_NULL_HANDLE;  // carbon-gsr2 capa\n",
             "capa pipeline")
    s = once(s, "    VkDescriptorSet conjunto_escalar = VK_NULL_HANDLE;\n",
             "    VkDescriptorSet conjunto_escalar = VK_NULL_HANDLE;\n    VkDescriptorSet conjunto_componer = VK_NULL_HANDLE;  // carbon-gsr2 capa\n", "capa ranura")
    s = once(s, "  VkShaderModule fs_escalar_ = VK_NULL_HANDLE;\n",
             "  VkShaderModule fs_escalar_ = VK_NULL_HANDLE;\n  VkShaderModule fs_componer_ = VK_NULL_HANDLE;  // carbon-gsr2 capa\n", "capa member fs")
    s = once(s, "  VkPipeline pipeline_escalar_ = VK_NULL_HANDLE;\n",
             "  VkPipeline pipeline_escalar_ = VK_NULL_HANDLE;\n  VkPipeline pipeline_componer_ = VK_NULL_HANDLE;  // carbon-gsr2 capa\n"
             "  std::vector<Imagen> compuesta_;  // carbon-gsr2 capa: per slot, the upscaled scene with the HUD layer over it\n",
             "capa member pipeline")
    s = once(s, "    DestruirImagen(historia_[1]);\n    ancho_render_ = alto_render_ = ancho_salida_ = alto_salida_ = 0;\n",
             "    DestruirImagen(historia_[1]);\n"
             "    for (Imagen& c : compuesta_) {  // carbon-gsr2 capa\n"
             "      DestruirImagen(c);\n"
             "    }\n"
             "    ancho_render_ = alto_render_ = ancho_salida_ = alto_salida_ = 0;\n", "capa destroy")
    s = once(s, "    return historia_[actual].vista;\n  }\n\n private:\n",
             "    // carbon-gsr2 capa: the HUD layer over the upscaled scene. The history keeps the scene alone.\n"
             "    if (e.capa != VK_NULL_HANDLE && pipeline_componer_ != VK_NULL_HANDLE && r.conjunto_componer != VK_NULL_HANDLE) {\n"
             "      if (compuesta_.size() != porRanura_.size()) {\n"
             "        compuesta_.resize(porRanura_.size());\n"
             "      }\n"
             "      Imagen& c = compuesta_[ranura];\n"
             "      if (c.imagen == VK_NULL_HANDLE) {\n"
             "        if (CrearImagen(c, ancho_salida, alto_salida)) {\n"
             "          VkImageMemoryBarrier b{};\n"
             "          b.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;\n"
             "          b.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;\n"
             "          b.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;\n"
             "          b.newLayout = VK_IMAGE_LAYOUT_GENERAL;\n"
             "          b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;\n"
             "          b.image = c.imagen;\n"
             "          b.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};\n"
             "          dfn_.vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT,\n"
             "                                    VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT, 0, 0, nullptr, 0, nullptr, 1, &b);\n"
             "        } else {\n"
             "          DestruirImagen(c);\n"
             "        }\n"
             "      }\n"
             "      if (c.imagen != VK_NULL_HANDLE) {\n"
             "        VkDescriptorImageInfo imagenes_k[3] = {{VK_NULL_HANDLE, historia_[actual].vista, VK_IMAGE_LAYOUT_GENERAL},\n"
             "                                               {VK_NULL_HANDLE, e.capa, VK_IMAGE_LAYOUT_GENERAL},\n"
             "                                               {VK_NULL_HANDLE, historia_[actual].vista, VK_IMAGE_LAYOUT_GENERAL}};\n"
             "        VkWriteDescriptorSet escritura_k{};\n"
             "        escritura_k.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;\n"
             "        escritura_k.dstSet = r.conjunto_componer;\n"
             "        escritura_k.dstBinding = 1;\n"
             "        escritura_k.descriptorCount = 3;\n"
             "        escritura_k.descriptorType = VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;\n"
             "        escritura_k.pImageInfo = imagenes_k;\n"
             "        dfn_.vkUpdateDescriptorSets(device_, 1, &escritura_k, 0, nullptr);\n"
             "        Pasada(cmd, c, ancho_salida, alto_salida, pipeline_componer_, r.conjunto_componer);\n"
             "        dfn_.vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,\n"
             "                                  VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT, 0, 1, &entre, 0, nullptr, 0, nullptr);\n"
             "        return c.vista;\n"
             "      }\n"
             "    }\n"
             "    return historia_[actual].vista;\n  }\n\n private:\n", "capa compose")
    s = once(s, '                  e.rect_profundidad[3], mascara ? "si" : "no (sin la copia de la escena)");\n',
             '                  e.rect_profundidad[3],\n'
             '                  e.capa != VK_NULL_HANDLE ? "no hace falta (el HUD va en una capa a la resolucion de la pantalla)"\n'
             '                                           : (mascara ? "si" : "no (sin la copia de la escena)"));\n', "capa log")
    wr(g, s)
    print("gsr2 cpp: HUD layer composition added")

# ---- dibujos.cpp: the scaled pass, per axis, for the layer's image
pd = APP + "/nfsmw_nativo_dibujos.cpp"
sd = rd(pd)
if "carbon-gsr2 capa" not in sd:
    sd = once(sd, "  float pase_escala_ = 1.0f;  // 1 except in the scaled shadow map\n",
              "  float pase_escala_ = 1.0f;  // 1 except in the scaled shadow map\n"
              "  float pase_escala_y_ = 1.0f;  // carbon-gsr2 capa: the same on the vertical axis\n"
              "  bool pase_capa_ = false;      // carbon-gsr2 capa: the pass draws into the HUD layer\n", "capa members")
    sd = once(sd, "    if (pase_escala_ != 1.0f) {\n      escala_x *= pase_escala_;\n      centro_x *= pase_escala_;\n"
                  "      escala_y *= pase_escala_;\n      centro_y *= pase_escala_;\n    }\n",
              "    if (pase_escala_ != 1.0f || pase_escala_y_ != 1.0f) {  // carbon-gsr2 capa: per axis\n"
              "      escala_x *= pase_escala_;\n      centro_x *= pase_escala_;\n"
              "      escala_y *= pase_escala_y_;\n      centro_y *= pase_escala_y_;\n    }\n", "capa viewport")
    sd = once(sd, "    if (pase_escala_ != 1.0f) {  // also in guest pixels\n"
                  "      x0 = int32_t(std::floor(float(x0) * pase_escala_));\n"
                  "      y0 = int32_t(std::floor(float(y0) * pase_escala_));\n"
                  "      x1 = int32_t(std::ceil(float(x1) * pase_escala_));\n"
                  "      y1 = int32_t(std::ceil(float(y1) * pase_escala_));\n    }\n",
              "    if (pase_escala_ != 1.0f || pase_escala_y_ != 1.0f) {  // also in guest pixels (carbon-gsr2 capa: per axis)\n"
              "      x0 = int32_t(std::floor(float(x0) * pase_escala_));\n"
              "      y0 = int32_t(std::floor(float(y0) * pase_escala_y_));\n"
              "      x1 = int32_t(std::ceil(float(x1) * pase_escala_));\n"
              "      y1 = int32_t(std::ceil(float(y1) * pase_escala_y_));\n    }\n", "capa scissor")
    sd = once(sd, "    if (area_util_) {\n      const auto it = alto_util_.find(pitch);\n",
              "    if (area_util_ && !(imagenes[0] && imagenes[0]->ancho_guest)) {  // carbon-gsr2 capa: not the HUD layer\n"
              "      const auto it = alto_util_.find(pitch);\n", "capa area")
    sd = once(sd, "    if (area_util_) {\n      const uint32_t hasta = ",
              "    if (area_util_ && !pase_capa_) {  // carbon-gsr2 capa: the layer's scissors are in output pixels\n"
              "      const uint32_t hasta = ", "capa area record")
    sd = once(sd, "    pase_escala_ = (es_sombras && pitch && ancho && ancho != pitch)\n"
                  "                       ? float(ancho) / float(pitch)\n"
                  "                       : 1.0f;\n",
              "    pase_escala_ = (es_sombras && pitch && ancho && ancho != pitch)\n"
              "                       ? float(ancho) / float(pitch)\n"
              "                       : 1.0f;\n"
              "    pase_escala_y_ = pase_escala_;\n"
              "    pase_capa_ = false;\n"
              "    if (imagenes[0] && imagenes[0]->ancho_guest && imagenes[0]->alto_guest) {  // carbon-gsr2 capa\n"
              "      pase_escala_ = float(imagenes[0]->ancho) / float(imagenes[0]->ancho_guest);\n"
              "      pase_escala_y_ = float(imagenes[0]->alto) / float(imagenes[0]->alto_guest);\n"
              "      pase_capa_ = true;\n"
              "    }\n", "capa pass scale")
    wr(pd, sd)
    print("patched nfsmw_nativo_dibujos.cpp (HUD layer scale)")

# ---- destinos.cpp
p5 = APP + "/nfsmw_nativo_destinos.cpp"
s5 = rd(p5)
if "carbon-gsr2 capa" not in s5:
    s5 = once(s5, "REXCVAR_DEFINE_BOOL(nfsmw_nativo_resolver_sin_copia, true, \"NFSMW\",\n",
              "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_hud_nativo, true, \"NFSMW\",\n"
              "                    \"Snapdragon GSR 2: el HUD y los menus se dibujan a la resolucion de la pantalla encima de la escena ya \"\n"
              "                    \"escalada (carbon-gsr2 capa). false = se escalan con el resto del fotograma\");\n"
              "REXCVAR_DEFINE_BOOL(nfsmw_nativo_resolver_sin_copia, true, \"NFSMW\",\n", "capa cvar")
    s5 = once(s5, "  bool Dibujar(const PeticionDibujo& peticion) override {\n    if (gsr_rt_ != 0) {\n      GsrAntesDeDibujo(peticion);  // carbon-gsr2: the scene before the HUD\n    }\n",
              "  bool Dibujar(const PeticionDibujo& peticion) override {\n"
              "    PeticionDibujo en_capa;  // carbon-gsr2 capa: the same draw with the HUD layer as target\n"
              "    const PeticionDibujo* a_dibujar = &peticion;\n"
              "    if (gsr_rt_ != 0) {\n"
              "      GsrAntesDeDibujo(peticion);  // carbon-gsr2: the scene before the HUD\n"
              "      if (GsrRedirigir(peticion, en_capa)) {\n"
              "        a_dibujar = &en_capa;\n"
              "      }\n"
              "    }\n", "capa dibujar head")
    s5 = once(s5, "    return dibujos_ && dibujos_->Dibujar(peticion);\n  }\n\n  EstadisticasDibujos EstadisticasDeDibujos() const override {",
              "    return dibujos_ && dibujos_->Dibujar(*a_dibujar);\n  }\n\n  EstadisticasDibujos EstadisticasDeDibujos() const override {", "capa dibujar tail")
    s5 = once(s5, "  ImagenNativa* DestinoColor(uint32_t base, uint32_t formato, uint32_t pitch) override {\n    Imagen* imagen = ObtenerDestino(base, formato, pitch);\n",
              "  ImagenNativa* DestinoColor(uint32_t base, uint32_t formato, uint32_t pitch) override {\n"
              "    if (base == kBaseCapaGsr && gsr_capa_activa_) {  // carbon-gsr2 capa: the HUD layer\n"
              "      Imagen& capa = gsr_capa_[gsr_capa_indice_];\n"
              "      if (!capa.imagen || !Grabar()) {\n"
              "        return nullptr;\n"
              "      }\n"
              "      Preparar(capa);\n"
              "      return &capa;\n"
              "    }\n"
              "    Imagen* imagen = ObtenerDestino(base, formato, pitch);\n", "capa destino color")
    s5 = once(s5, "    Destruir(mosaico_);\n",
              "    Destruir(mosaico_);\n    for (Imagen& capa : gsr_capa_) {  // carbon-gsr2 capa\n      Destruir(capa);\n    }\n", "capa destroy")
    s5 = once(s5, "  void GsrFinDeFotograma() {\n",
              r'''  // ---- carbon-gsr2 capa: the HUD drawn at the output's resolution ----------------------------------------------
  // EDRAM base that no render target of the game uses (there are 2048 tiles): the draws that go to the layer are
  // given this base in a copy of their registers, and DestinoColor answers with the layer.
  static constexpr uint32_t kBaseCapaGsr = 0xFFE;
  static constexpr uint32_t kCapasGsr = 4;  // a layer is read by the output of its frame: 3 outputs in flight + the one drawn

  bool GsrCapasListas() {
    if (!gsr_capa_permitida_ || !gsr2_ || !gsr_capa_prevista_ || !gsr_salida_ancho_ || !gsr_salida_alto_) {
      return false;
    }
    const int32_t gw = gsr_rect_[2] - gsr_rect_[0], gh = gsr_rect_[3] - gsr_rect_[1];
    if (gsr_rect_[0] != 0 || gsr_rect_[1] != 0 || gw <= 0 || gh <= 0) {
      return false;  // the HUD's coordinates start at the corner of the render target
    }
    if (!gsr_capa_[0].imagen) {
      for (uint32_t i = 0; i < kCapasGsr; ++i) {
        if (!Crear(gsr_capa_[i], gsr_salida_ancho_, gsr_salida_alto_,
                   VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
                   FormatoHostDestinoColor(0))) {  // 8888: the layer clamps like the game's own HUD target (no NaN/out-of-range colors)
          for (uint32_t j = 0; j <= i; ++j) {
            Destruir(gsr_capa_[j]);
          }
          gsr_capa_permitida_ = false;
          REXLOG_ERROR("[gsr2] no se pudieron crear las capas del HUD ({}x{}): el HUD se escala como siempre",
                       gsr_salida_ancho_, gsr_salida_alto_);
          return false;
        }
      }
      REXLOG_INFO("[gsr2] capas del HUD: {} de {}x{} (el HUD del juego, de {}x{}, se dibuja a ese tamano)", kCapasGsr,
                  gsr_salida_ancho_, gsr_salida_alto_, gw, gh);
    }
    if (gsr_capa_[0].ancho != gsr_salida_ancho_ || gsr_capa_[0].alto != gsr_salida_alto_) {
      return false;  // the output changed size: no layer until it is back
    }
    for (Imagen& capa : gsr_capa_) {
      capa.ancho_guest = uint32_t(gw);  // the size the game thinks the target has: the pass scale comes from it
      capa.alto_guest = uint32_t(gh);
    }
    return true;
  }

  // The first HUD draw of the frame: the next layer, cleared.
  bool GsrIniciarCapa() {
    if (!GsrCapasListas() || !Grabar() || !dibujos_) {
      return false;
    }
    dibujos_->TerminarPase();
    const uint32_t siguiente = (gsr_capa_indice_ + 1) % kCapasGsr;
    Imagen& capa = gsr_capa_[siguiente];
    Preparar(capa);
    if (!capa.preparada) {
      return false;
    }
    VkMemoryBarrier antes{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
    antes.srcAccessMask = kAccesosImagenes;
    antes.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    dfn_.vkCmdPipelineBarrier(comandos_trabajo_, kEtapasImagenes, VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &antes, 0,
                              nullptr, 0, nullptr);
    const VkClearColorValue transparente{};
    dfn_.vkCmdClearColorImage(comandos_trabajo_, capa.imagen, VK_IMAGE_LAYOUT_GENERAL, &transparente, 1, &kRangoColor);
    VkMemoryBarrier despues{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
    despues.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
    despues.dstAccessMask = kAccesosImagenes;
    dfn_.vkCmdPipelineBarrier(comandos_trabajo_, VK_PIPELINE_STAGE_TRANSFER_BIT, kEtapasImagenes, 0, 1, &despues, 0,
                              nullptr, 0, nullptr);
    gsr_capa_indice_ = siguiente;
    gsr_capa_activa_ = true;
    gsr_capa_valida_ = true;
    gsr_capa_dibujos_ = 0;
    return true;
  }

  // The blend of a draw into the layer. The layer holds premultiplied color and coverage: "over" accumulates
  // both, additive leaves the coverage, an opaque draw replaces. The color part stays as the game set it.
  uint32_t GsrMezclaCapa(uint32_t mezcla) {
    const uint32_t origen = mezcla & 0x1F, destino = (mezcla >> 8) & 0x1F;
    uint32_t a_origen = 1, a_destino = 7;  // coverage = src + dst * (1 - src)
    bool conocida = true;
    if (origen == 1 && destino == 0) {
      a_destino = 0;  // opaque: replaces
    } else if (destino == 7 || destino == 5) {
      a_destino = 7;  // over (SRC_ALPHA / ONE with ONE_MINUS_SRC_ALPHA, or the screen blend)
    } else if (destino == 1) {
      a_origen = 0;  // additive: the coverage stays
      a_destino = 1;
    } else {
      conocida = false;  // multiply and others have no equivalent in a layer: the coverage stays
      a_origen = 0;
      a_destino = 1;
    }
    const uint32_t nueva = (mezcla & 0x1FFFu) | (a_origen << 16) | (a_destino << 24);
    if (gsr_mezclas_avisadas_.size() < 24 &&
        std::find(gsr_mezclas_avisadas_.begin(), gsr_mezclas_avisadas_.end(), mezcla) == gsr_mezclas_avisadas_.end()) {
      gsr_mezclas_avisadas_.push_back(mezcla);
      REXLOG_INFO("[gsr2] capa del HUD: mezcla {:08X} -> {:08X}{}", mezcla, nueva,
                  conocida ? "" : " (SIN equivalente en la capa: la cobertura se queda)");
    }
    return nueva;
  }

  // A draw to the front render target: if it is HUD (no depth test), the same draw into the layer, with the
  // render target replaced in a copy of the registers. False = draw as it comes.
  bool GsrRedirigir(const PeticionDibujo& p, PeticionDibujo& salida) {
    if (!gsr_capa_cvar_leida_) {
      gsr_capa_cvar_leida_ = true;
      gsr_capa_permitida_ = REXCVAR_GET(nfsmw_gsr2_hud_nativo);
      REXLOG_INFO("[gsr2] HUD a la resolucion de la pantalla: {}", gsr_capa_permitida_ ? "si" : "no (nfsmw_gsr2_hud_nativo = false)");
    }
    if (!gsr_capa_permitida_ || !dibujos_) {
      return false;
    }
    const uint32_t* r = p.registros;
    if (!r || (r[gr::XE_GPU_REG_RB_MODECONTROL] & 0x7) != uint32_t(xenos::EdramMode::kColorDepth)) {
      return false;
    }
    const uint32_t info = r[gr::XE_GPU_REG_RB_COLOR_INFO];
    const uint32_t pitch = r[gr::XE_GPU_REG_RB_SURFACE_INFO] & 0x3FFF;
    if (!GsrEsElDestinoFrontal(info & 0xFFF, pitch) || (r[gr::XE_GPU_REG_RB_COLOR_MASK] & 0xF) == 0) {
      return false;
    }
    if (((r[gr::XE_GPU_REG_RB_DEPTHCONTROL] >> 1) & 0x1) != 0) {  // depth test: scene geometry
      if (gsr_capa_activa_) {
        gsr_capa_valida_ = false;  // scene after the HUD began: this frame cannot use the layer
      }
      return false;
    }
    if (!gsr_capa_activa_) {
      const uint32_t mezcla = r[gr::XE_GPU_REG_RB_BLENDCONTROL0];
      const bool opaco = (mezcla & 0x1F) == 1 && ((mezcla >> 8) & 0x1F) == 0;
      if (opaco || !gsr_vio_escena_ || !GsrIniciarCapa()) {
        return false;  // the full-screen composite of the scene (opaque) and anything before the HUD stay
      }
    }
    // The registers of the draw, with the layer as target (80 KB per draw: the HUD is 30-70 draws).
    gsr_registros_.assign(r, r + kRegistrosEspejo);
    gsr_registros_[gr::XE_GPU_REG_RB_COLOR_INFO] = (info & ~(0xFFFu | (0xFu << 16))) | kBaseCapaGsr;  // base of the layer, format k_8_8_8_8
    gsr_registros_[gr::XE_GPU_REG_RB_BLENDCONTROL0] = GsrMezclaCapa(r[gr::XE_GPU_REG_RB_BLENDCONTROL0]);
    const uint32_t mascara = r[gr::XE_GPU_REG_RB_COLOR_MASK];
    if ((mascara & 0x7) == 0x7) {
      gsr_registros_[gr::XE_GPU_REG_RB_COLOR_MASK] = mascara | 0x8;  // the coverage is always written
    }
    salida = p;
    salida.registros = gsr_registros_.data();
    ++gsr_capa_dibujos_;
    return true;
  }

  void GsrFinDeFotograma() {
    if (gsr_capa_activa_ && (gsr_fotogramas_ < 6 || gsr_fotogramas_ % 300 == 0)) {
      REXLOG_INFO("[gsr2] capa del HUD (fotograma {}): {} dibujos, {}", gsr_fotogramas_ + 1, gsr_capa_dibujos_,
                  gsr_capa_valida_ ? "valida" : "INVALIDA (escena despues del HUD: este fotograma sale sin ella)");
    }
    gsr_capa_activa_ = false;
    gsr_capa_valida_ = false;
    gsr_capa_dibujos_ = 0;
''', "capa functions")
    s5 = once(s5, "    plan.activo = true;\n  }\n",
              "    if (gsr_capa_activa_ && gsr_capa_valida_) {  // carbon-gsr2 capa\n"
              "      // The resolved front buffer holds the render target's channels as they are (intercambio_rb only changes how the\n"
              "      // game samples it), the same order as the layer.\n"
              "      e.capa = gsr_capa_[gsr_capa_indice_].vista;  // the front buffer has no HUD: the layer goes over the upscaled scene\n"
              "      e.escena = VK_NULL_HANDLE;                   // and there is nothing to mask\n"
              "    }\n"
              "    plan.activo = true;\n  }\n", "capa plan")
    s5 = once(s5, "    const bool con_gsr2 = plan_gsr2.activo && (plan_gsr2.ancho_salida > w || plan_gsr2.alto_salida > h);\n",
              "    const bool con_gsr2 = plan_gsr2.activo && (plan_gsr2.ancho_salida > w || plan_gsr2.alto_salida > h);\n"
              "    // carbon-gsr2 capa: the output's size for the HUD layers of the next frames, and this frame's layer only if it fits.\n"
              "    gsr_capa_prevista_ = con_gsr2;\n"
              "    if (con_gsr2) {\n"
              "      gsr_salida_ancho_ = plan_gsr2.ancho_salida;\n"
              "      gsr_salida_alto_ = plan_gsr2.alto_salida;\n"
              "      if (plan_gsr2.entradas.capa != VK_NULL_HANDLE &&\n"
              "          (gsr_capa_[gsr_capa_indice_].ancho != plan_gsr2.ancho_salida ||\n"
              "           gsr_capa_[gsr_capa_indice_].alto != plan_gsr2.alto_salida)) {\n"
              "        plan_gsr2.entradas.capa = VK_NULL_HANDLE;\n"
              "      }\n"
              "    } else {\n"
              "      plan_gsr2.entradas.capa = VK_NULL_HANDLE;\n"
              "    }\n", "capa present")
    s5 = once(s5, "  uint32_t gsr_fotogramas_ = 0;\n",
              "  uint32_t gsr_fotogramas_ = 0;\n"
              "  // carbon-gsr2 capa\n"
              "  static constexpr size_t kRegistrosEspejo = 0x5003;  // RegisterFile::kRegisterCount\n"
              "  Imagen gsr_capa_[4];\n"
              "  uint32_t gsr_capa_indice_ = 0;\n"
              "  bool gsr_capa_activa_ = false;      // the frame's HUD draws go to the layer\n"
              "  bool gsr_capa_valida_ = false;      // and nothing that belongs to the scene came after the first one\n"
              "  bool gsr_capa_prevista_ = false;    // the last frame went through GSR 2\n"
              "  bool gsr_capa_permitida_ = true;    // false if the layers could not be created or the setting is off\n"
              "  bool gsr_capa_cvar_leida_ = false;\n"
              "  uint32_t gsr_salida_ancho_ = 0, gsr_salida_alto_ = 0;\n"
              "  uint32_t gsr_capa_dibujos_ = 0;\n"
              "  std::vector<uint32_t> gsr_registros_;\n"
              "  std::vector<uint32_t> gsr_mezclas_avisadas_;\n", "capa members")
    wr(p5, s5)
    print("patched nfsmw_nativo_destinos.cpp (HUD layer)")

# ---- destinos.cpp: draw listing (diagnostic, off by default)
s6 = rd(p5)
if "carbon-gsr2 diag" not in s6:
    s6 = once(s6, "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_hud_nativo, true, \"NFSMW\",\n",
              "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_diag_dibujos, false, \"NFSMW\",\n"
              "                    \"Snapdragon GSR 2 (diagnostico, carbon-gsr2 diag): lista cada 450 fotogramas los dibujos al RT frontal \"\n"
              "                    \"(clase, shaders, mezcla, profundidad, viewport, tijera); maximo 3 listas con mas de 150 dibujos\");\n"
              "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_hud_nativo, true, \"NFSMW\",\n", "diag cvar")
    s6 = once(s6, "    const bool hud = !con_z && !opaco;\n    const uint32_t huella = p.ps ? uint32_t(p.ps->huella) : 0;\n",
              "    const bool hud = !con_z && !opaco;\n    const uint32_t huella = p.ps ? uint32_t(p.ps->huella) : 0;\n"
              "    if (gsr_diag_recoger_) {  // carbon-gsr2 diag\n"
              "      const uint32_t tl = r[gr::XE_GPU_REG_PA_SC_WINDOW_SCISSOR_TL], br = r[gr::XE_GPU_REG_PA_SC_WINDOW_SCISSOR_BR];\n"
              "      auto f = [&](uint32_t reg) { return std::bit_cast<float>(r[reg]); };\n"
              "      gsr_diag_ += fmt::format(\"  #{} {} VS n{} {:08X} PS n{} {:08X} mezcla {:08X} z {:08X} mascara {:X} vp x {:.0f}+-{:.0f} y {:.0f}+-{:.0f} tijera ({},{})-({},{})\\n\",\n"
              "                               gsr_diag_n_++, con_z ? 'S' : (opaco ? 'O' : 'H'), p.vs ? uint32_t(p.vs->numero) : 0,\n"
              "                               p.vs ? uint32_t(p.vs->huella) : 0, p.ps ? uint32_t(p.ps->numero) : 0, huella, mezcla, control_z,\n"
              "                               r[gr::XE_GPU_REG_RB_COLOR_MASK] & 0xF, f(gr::XE_GPU_REG_PA_CL_VPORT_XOFFSET),\n"
              "                               f(gr::XE_GPU_REG_PA_CL_VPORT_XSCALE), f(gr::XE_GPU_REG_PA_CL_VPORT_YOFFSET),\n"
              "                               f(gr::XE_GPU_REG_PA_CL_VPORT_YSCALE), tl & 0x3FFF, (tl >> 16) & 0x3FFF, br & 0x3FFF,\n"
              "                               (br >> 16) & 0x3FFF);\n"
              "    }\n", "diag collect")
    s6 = once(s6, "    if (gsr_capa_activa_ && (gsr_fotogramas_ < 6 || gsr_fotogramas_ % 300 == 0)) {\n",
              "    if (gsr_diag_recoger_) {  // carbon-gsr2 diag\n"
              "      gsr_diag_recoger_ = false;\n"
              "      if (gsr_diag_n_ > 150) {\n"
              "        ++gsr_diag_vuelcos_;\n"
              "        REXLOG_INFO(\"[gsr2] LISTA de dibujos al RT frontal (fotograma {}, {} dibujos):\", gsr_fotogramas_ + 1, gsr_diag_n_);\n"
              "        size_t desde = 0;\n"
              "        while (desde < gsr_diag_.size()) {\n"
              "          size_t hasta = gsr_diag_.find('\\n', desde);\n"
              "          if (hasta == std::string::npos) {\n"
              "            hasta = gsr_diag_.size();\n"
              "          }\n"
              "          REXLOG_INFO(\"[gsr2]{}\", std::string_view(gsr_diag_).substr(desde, hasta - desde));\n"
              "          desde = hasta + 1;\n"
              "        }\n"
              "      }\n"
              "      gsr_diag_.clear();\n"
              "      gsr_diag_n_ = 0;\n"
              "    }\n"
              "    if (!gsr_diag_cvar_leida_) {\n"
              "      gsr_diag_cvar_leida_ = true;\n"
              "      gsr_diag_activo_ = REXCVAR_GET(nfsmw_gsr2_diag_dibujos);\n"
              "    }\n"
              "    if (gsr_diag_activo_ && gsr_diag_vuelcos_ < 3 && (gsr_fotogramas_ + 1) % 450 == 0) {\n"
              "      gsr_diag_recoger_ = true;  // the next frame is listed\n"
              "      gsr_diag_n_ = 0;\n"
              "    }\n"
              "    if (gsr_capa_activa_ && (gsr_fotogramas_ < 6 || gsr_fotogramas_ % 300 == 0)) {\n", "diag dump")
    s6 = once(s6, "  std::vector<uint32_t> gsr_registros_;\n",
              "  std::vector<uint32_t> gsr_registros_;\n"
              "  // carbon-gsr2 diag\n"
              "  std::string gsr_diag_;\n"
              "  uint32_t gsr_diag_n_ = 0, gsr_diag_vuelcos_ = 0;\n"
              "  bool gsr_diag_recoger_ = false, gsr_diag_cvar_leida_ = false, gsr_diag_activo_ = false;\n", "diag members")
    wr(p5, s6)
    print("patched nfsmw_nativo_destinos.cpp (draw listing)")

# ---- destinos.cpp: layer experiments (diagnostic, off by default)
s7 = rd(p5)
if "carbon-gsr2 diag2" not in s7:
    s7 = once(s7, "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_hud_nativo, true, \"NFSMW\",\n",
              "REXCVAR_DEFINE_INT32(nfsmw_gsr2_diag_capa, 0, \"NFSMW\",\n"
              "                     \"Snapdragon GSR 2 (diagnostico, carbon-gsr2 diag2): mascara de pruebas de la capa del HUD. 1 = no dibuja \"\n"
              "                     \"los dibujos con VS 72; 2 = no dibuja los aditivos; 4 = no dibuja los de mezcla normal (salvo VS 72); \"\n"
              "                     \"8 = capa a la escala del juego (sin 1.248)\");\n"
              "REXCVAR_DEFINE_BOOL(nfsmw_gsr2_hud_nativo, true, \"NFSMW\",\n", "diag2 cvar")
    s7 = once(s7, "      gsr_capa_permitida_ = REXCVAR_GET(nfsmw_gsr2_hud_nativo);\n",
              "      gsr_capa_permitida_ = REXCVAR_GET(nfsmw_gsr2_hud_nativo);\n"
              "      gsr_diag_capa_ = uint32_t(REXCVAR_GET(nfsmw_gsr2_diag_capa));  // carbon-gsr2 diag2\n"
              "      if (gsr_diag_capa_) {\n"
              "        REXLOG_INFO(\"[gsr2] PRUEBAS de la capa del HUD, mascara {}\", gsr_diag_capa_);\n"
              "      }\n", "diag2 read")
    s7 = once(s7, "    salida = p;\n    salida.registros = gsr_registros_.data();\n    ++gsr_capa_dibujos_;\n",
              "    salida = p;\n    salida.registros = gsr_registros_.data();\n    ++gsr_capa_dibujos_;\n"
              "    if (gsr_diag_capa_) {  // carbon-gsr2 diag2\n"
              "      const uint32_t m = r[gr::XE_GPU_REG_RB_BLENDCONTROL0];\n"
              "      const bool aditivo = ((m >> 8) & 0x1F) == 1 && (m & 0x1F) != 1;\n"
              "      const bool vs72 = p.vs && p.vs->numero == 72;\n"
              "      if (((gsr_diag_capa_ & 1) && vs72) || ((gsr_diag_capa_ & 2) && aditivo) ||\n"
              "          ((gsr_diag_capa_ & 4) && !aditivo && !vs72)) {\n"
              "        gsr_descartar_ = true;\n"
              "      }\n"
              "    }\n", "diag2 drop")
    s7 = once(s7, "      if (GsrRedirigir(peticion, en_capa)) {\n        a_dibujar = &en_capa;\n",
              "      if (GsrRedirigir(peticion, en_capa)) {\n        a_dibujar = &en_capa;\n"
              "        if (gsr_descartar_) {  // carbon-gsr2 diag2\n"
              "          gsr_descartar_ = false;\n"
              "          return true;\n"
              "        }\n", "diag2 dibujar")
    s7 = once(s7, "      capa.ancho_guest = uint32_t(gw);  // the size the game thinks the target has: the pass scale comes from it\n"
                  "      capa.alto_guest = uint32_t(gh);\n",
              "      capa.ancho_guest = uint32_t(gw);  // the size the game thinks the target has: the pass scale comes from it\n"
              "      capa.alto_guest = uint32_t(gh);\n"
              "      if (gsr_diag_capa_ & 8) {  // carbon-gsr2 diag2: no scale\n"
              "        capa.ancho_guest = capa.ancho;\n"
              "        capa.alto_guest = capa.alto;\n"
              "      }\n", "diag2 scale")
    s7 = once(s7, "  // carbon-gsr2 diag\n  std::string gsr_diag_;\n",
              "  // carbon-gsr2 diag2\n  uint32_t gsr_diag_capa_ = 0;\n  bool gsr_descartar_ = false;\n"
              "  // carbon-gsr2 diag\n  std::string gsr_diag_;\n", "diag2 members")
    wr(p5, s7)
    print("patched nfsmw_nativo_destinos.cpp (layer experiments)")

# ---- destinos.cpp: textures of the additive HUD draws + split of the additive test (diagnostic)
s8 = rd(p5)
if "carbon-gsr2 diag3" not in s8:
    s8 = once(s8, "                               (br >> 16) & 0x3FFF);\n    }\n",
              "                               (br >> 16) & 0x3FFF);\n"
              "      if (!con_z && !opaco && ((mezcla >> 8) & 0x1F) == 1 && (mezcla & 0x1F) != 1) {  // carbon-gsr2 diag3: additive HUD\n"
              "        std::string t;\n"
              "        for (uint32_t i = 0; i < 16; ++i) {\n"
              "          const uint32_t* c = r + gr::XE_GPU_REG_SHADER_CONSTANT_FETCH_00_0 + i * 6;\n"
              "          if (c[1] & 0xFFFFF000u) {\n"
              "            t += fmt::format(\" s{}:{:08X} {}x{} fmt{} tipo{}\", i, c[1] & 0xFFFFF000u, (c[2] & 0x1FFF) + 1,\n"
              "                             ((c[2] >> 13) & 0x1FFF) + 1, c[1] & 0x3F, c[0] & 3);\n"
              "          }\n"
              "        }\n"
              "        gsr_diag_ += fmt::format(\"       texturas:{}\\n\", t);\n"
              "      }\n"
              "    }\n", "diag3 textures")
    s8 = once(s8, "      if (((gsr_diag_capa_ & 1) && vs72) || ((gsr_diag_capa_ & 2) && aditivo) ||\n",
              "      if (((gsr_diag_capa_ & 16) && aditivo && gsr_capa_dibujos_ <= 100) ||  // carbon-gsr2 diag3\n"
              "          ((gsr_diag_capa_ & 32) && aditivo && gsr_capa_dibujos_ > 100) ||\n"
              "          ((gsr_diag_capa_ & 1) && vs72) || ((gsr_diag_capa_ & 2) && aditivo) ||\n", "diag3 split")
    wr(p5, s8)
    print("patched nfsmw_nativo_destinos.cpp (diag3)")

# ---------------------------------------------------------------- 5. Carbon: CMake + camera hooks
p = C + "/CMakeLists.txt"
s = rd(p)
if "nfsmw_gsr2.cpp" in s:
    print("CMakeLists already has gsr2")
else:
    s = once(s, "    ${NFSC_NFSMW_SRC}/nfsmw_ajustes_graficos.cpp)\n",
             "    ${NFSC_NFSMW_SRC}/nfsmw_ajustes_graficos.cpp\n    ${NFSC_NFSMW_SRC}/nfsmw_gsr2.cpp)\n", "cmake")
    wr(p, s)
    print("patched CMakeLists.txt")

p = C + "/android/app/src/main/cpp/carbon_graphics.cpp"
s = rd(p)
if "carbon-gsr2" in s:
    # first version hooked sub_82453428 (the render thread's whole loop): move the bracket to sub_82453048.
    # The old block is the last thing in the file; it starts at a comment line ("//", or "#" if an editor changed it).
    import re
    m = re.search(r"\n(?://|#) carbon-gsr2: one camera", s)
    if m and s[m.start():] != HOOK_BLOCK:
        s = s[:m.start()] + HOOK_BLOCK
        wr(p, s)
        print("carbon_graphics.cpp: frame hook moved to sub_82453048")
    else:
        print("carbon_graphics.cpp already patched")
else:
    if "carbon-ws2" not in s:
        sys.exit("carbon_graphics.cpp lacks the widescreen v2 patch (needed: this step hooks its camera functions)")
    s = once(s, "#include <SDL3/SDL_video.h>\n", "#include <SDL3/SDL_video.h>\n#include \"nfsmw_gsr2.h\"  // carbon-gsr2\n", "cg include")
    s = once(s, "  __imp__sub_822CEC80(ctx, base);\n",
             "  __imp__sub_822CEC80(ctx, base);\n"
             "  // carbon-gsr2: the view x projection (block + 192) is final here; view 1's is the camera of the frame.\n"
             "  if (t_block && t_view && verified && CameraCodeIsCarbon(base)) nfsmw::gsr2::TrasUpdate(base, t_view, t_block);\n",
             "cg cec80")
    s = once(s, "  __imp__sub_822CEA90(ctx, base);\n",
             "  __imp__sub_822CEA90(ctx, base);\n"
             "  // carbon-gsr2: at the end of this hook (after the widescreen correction) the frame's jitter goes into the projection\n"
             "  // (+64 and its copy +128), before sub_822CEC80 multiplies it by the view.\n"
             "  struct Gsr2Jitter {\n"
             "    uint8_t* base;\n"
             "    ~Gsr2Jitter() {\n"
             "      if (t_block && t_view && verified && CameraCodeIsCarbon(base)) {\n"
             "        nfsmw::gsr2::AjustarProyeccion(base, t_view, t_block + 64);\n"
             "        nfsmw::gsr2::AjustarProyeccion(base, t_view, t_block + 128);\n"
             "      }\n"
             "    }\n"
             "  } gsr2_jitter{base};\n", "cg cea90")
    s += HOOK_BLOCK
    wr(p, s)
    print("patched carbon_graphics.cpp")