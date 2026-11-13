/* Storage and export for the shadow-batch trace (shadow_trace.h). Built only
 * with BLUEWAKE_SHADOW_TRACE. */
#include "shadow_trace.h"

#if defined(_WIN32)
#define BW_SHADOW_TRACE_EXPORT __declspec(dllexport)
#else
#define BW_SHADOW_TRACE_EXPORT __attribute__((visibility("default")))
#endif

BwShadowTrace bw_shadow_trace = {.version = 1u};

BW_SHADOW_TRACE_EXPORT BwShadowTrace* bluewake_composite_shadow_trace(void) {
    return &bw_shadow_trace;
}
