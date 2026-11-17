import sys

root = sys.argv[1]  # nfsmw-android/app/src


def patch(path, edits):
    s = open(path, encoding="utf-8").read()
    for marker, old, new in edits:
        if marker in s:
            print("ya aplicado:", marker)
            continue
        n = s.count(old)
        if n != 1:
            sys.exit("ANCLA NO ENCONTRADA (%d veces) para %s: %r" % (n, marker, old[:60]))
        s = s.replace(old, new, 1)
        print("aplicado:", marker)
    open(path, "w", encoding="utf-8").write(s)


D = root + "/nfsmw_nativo_dibujos.cpp"
patch(D, [
    ("carbon-c173-inc", "#include <cmath>\n", "#include <cmath>\n#include <cstdlib>  // carbon-c173-inc\n"),
    ("carbon-c173-cvar",
     '"se graban (solo pruebas, para localizar un dibujo)");\n',
     '"se graban (solo pruebas, para localizar un dibujo)");\n'
     '// carbon-c173-cvar: override of c173 (cvBlurParams) of one pixel shader, for tests.\n'
     'REXCVAR_DEFINE_INT32(carbon_c173_ps, -1, "Carbon",\n'
     '                     "Number of the pixel shader whose constant c173 (cvBlurParams) is overridden (-1 = off)");\n'
     'REXCVAR_DEFINE_STRING(carbon_c173_valor, "x,x,x,x", "Carbon",\n'
     '                      "x,y,z,w written to c173 of that pixel shader; x = keep the game value");\n'
     'REXCVAR_DEFINE_DOUBLE(carbon_c173_escala, 1.0, "Carbon",\n'
     '                      "Multiplies the game\'s own blur strength (c173.x) of that pixel shader: 0.4 = 40 %, still grows with speed");\n'
     'REXCVAR_DEFINE_DOUBLE(carbon_c173_max, -1.0, "Carbon",\n'
     '                      "The game\'s own blur strength (c173.x) never goes above this (negative = no limit)");\n'),
    ("carbon-c173-members",
     "  std::string diag_omitir_ps_texto_;\n",
     "  std::string diag_omitir_ps_texto_;\n"
     "  int32_t carbon_c173_ps_ = -1;  // carbon-c173-members\n"
     "  float carbon_c173_v_[4] = {NAN, NAN, NAN, NAN};\n"
     "  std::string carbon_c173_texto_;\n"
     "  float carbon_c173_escala_ = 1.0f;\n"
     "  float carbon_c173_max_ = -1.0f;\n"),
    ("carbon-c173-frame",
     "    diag_omitir_ps_texto_ = REXCVAR_GET(nfsmw_nativo_diag_omitir_ps);\n",
     "    diag_omitir_ps_texto_ = REXCVAR_GET(nfsmw_nativo_diag_omitir_ps);\n"
     "    // carbon-c173-frame\n"
     "    carbon_c173_ps_ = REXCVAR_GET(carbon_c173_ps);\n"
     "    if (carbon_c173_ps_ >= 0) {\n"
     "      carbon_c173_escala_ = float(REXCVAR_GET(carbon_c173_escala));\n"
     "      carbon_c173_max_ = float(REXCVAR_GET(carbon_c173_max));\n"
     "      const std::string v = REXCVAR_GET(carbon_c173_valor);\n"
     "      if (v != carbon_c173_texto_) {\n"
     "        carbon_c173_texto_ = v;\n"
     "        size_t ini = 0;\n"
     "        for (int k = 0; k < 4; ++k) {\n"
     "          const size_t fin = std::min(v.find(',', ini), v.size());\n"
     "          const std::string t = v.substr(ini, fin - ini);\n"
     "          carbon_c173_v_[k] = (t.empty() || t[0] == 'x') ? NAN : std::strtof(t.c_str(), nullptr);\n"
     "          ini = std::min(fin + 1, v.size());\n"
     "        }\n"
     "        REXLOG_WARN(\"[carbon] c173 del PS {} = ({}, {}, {}, {}) (nan = el del juego)\", carbon_c173_ps_,\n"
     "                    carbon_c173_v_[0], carbon_c173_v_[1], carbon_c173_v_[2], carbon_c173_v_[3]);\n"
     "      }\n"
     "    }\n"),
    ("carbon-c173-func",
     "  bool Reservar(VkDeviceSize bytes, VkDeviceSize alineacion, VkDeviceSize& offset) {\n",
     "  // carbon-c173-func: uploads its own copy of the constants of the chosen pixel shader with c173 (cvBlurParams)\n"
     "  // changed, and leaves the cache empty so the next draw uploads the game's (like CopiaComposicionTratada).\n"
     "  [[gnu::noinline]] void CopiaC173(const EntradaShader* ps, const uint32_t* r, uint32_t bytes_ps) noexcept {\n"
     "    if (carbon_c173_ps_ < 0 || !ps || ps->numero != uint32_t(carbon_c173_ps_) || bytes_ps < 174 * 16) {\n"
     "      return;\n"
     "    }\n"
     "    VkDeviceSize offset = 0;\n"
     "    if (!Reservar(usar_ubo_ ? std::max<VkDeviceSize>(bytes_ps, kUboBytesPs) : bytes_ps,\n"
     "                  usar_ubo_ ? alineacion_ubo_ : 16, offset)) {\n"
     "      return;\n"
     "    }\n"
     "    std::memcpy(subida_datos_ + offset, r + kRegConstantesPs, bytes_ps);\n"
     "    float* c = reinterpret_cast<float*>(subida_datos_ + offset) + 173 * 4;\n"
     "    for (int k = 0; k < 4; ++k) {\n"
     "      if (!std::isnan(carbon_c173_v_[k])) {\n"
     "        c[k] = carbon_c173_v_[k];\n"
     "      }\n"
     "    }\n"
     "    if (std::isnan(carbon_c173_v_[0]) && std::isfinite(c[0])) {  // the game's own strength: scaled and limited\n"
     "      float x = c[0] * carbon_c173_escala_;\n"
     "      if (carbon_c173_max_ >= 0.0f) {\n"
     "        x = std::min(x, carbon_c173_max_);\n"
     "      }\n"
     "      c[0] = x;\n"
     "    }\n"
     "    constantes_ps_offset_ = offset;\n"
     "    constantes_ps_generacion_ = UINT64_MAX;\n"
     "  }\n\n"
     "  bool Reservar(VkDeviceSize bytes, VkDeviceSize alineacion, VkDeviceSize& offset) {\n"),
    ("carbon-c173-call",
     "    if (!ps || !ps->shader || ps->shader->huella != kHuellaComposicion) {\n      return;\n    }\n"
     "    const int modo = nfsmw::ajustes::TratamientoVisual();\n",
     "    CopiaC173(ps, r, bytes_ps);  // carbon-c173-call\n"
     "    if (!ps || !ps->shader || ps->shader->huella != kHuellaComposicion) {\n      return;\n    }\n"
     "    const int modo = nfsmw::ajustes::TratamientoVisual();\n"),
])

S = root + "/nfsmw_nativo_sistema.cpp"
patch(S, [
    ("carbon-c173-diag",
     '    REXLOG_INFO("[nativo] constantes PS n{} (Swap {}):{}", ps_dibujo_->numero, swaps_.load(), valores);\n',
     '    for (uint32_t k : {173u, 255u}) {  // carbon-c173-diag: cvBlurParams and c255\n'
     '      valores += fmt::format(" c{}=(", k);\n'
     '      for (uint32_t c = 0; c < 4; ++c) {\n'
     '        float f;\n'
     '        const uint32_t bits = registros_[0x4400 + k * 4 + c];\n'
     '        std::memcpy(&f, &bits, sizeof(f));\n'
     '        valores += fmt::format("{}{:.4g}", c ? "," : "", f);\n'
     '      }\n'
     '      valores += ")";\n'
     '    }\n'
     '    REXLOG_INFO("[nativo] constantes PS n{} (Swap {}):{}", ps_dibujo_->numero, swaps_.load(), valores);\n'),
])
