// Native TGL hwSetBacklight uses floor(period * brightness / 65535).
// Keep a visible minimum without taking over native panel power handling.
#ifndef KERN_TGL_BACKLIGHT_HPP
#define KERN_TGL_BACKLIGHT_HPP
#include <stdint.h>
namespace TGLBacklight {
inline uint32_t minimumRequest(uint32_t brightness,uint32_t period,uint32_t vbtMinimum=0) {
    // Preserve native startup and invalid-input handling when no period exists.
    if(brightness>65535 || !period || period==UINT32_MAX)return brightness;
    const auto first=uint32_t((65535ULL+period-1)/period);
    // i915 treats the VBT minimum as a coefficient out of 255 and caps
    // malformed firmware values at 64. No fixed percentage is substituted.
    const auto coefficient=vbtMinimum>64?64:vbtMinimum;
    const auto firmware=uint32_t((uint64_t(coefficient)*65535+254)/255);
    const auto minimum=first>firmware?first:firmware;
    return minimum+uint32_t((uint64_t(65535-minimum)*brightness+32767)/65535);
}
}
#endif
