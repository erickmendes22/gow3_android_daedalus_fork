/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef SOTC_ANDROID_LOWMEM_H
#define SOTC_ANDROID_LOWMEM_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
void *sotc_map_guest_image(size_t bytes);
void sotc_unmap_guest_image(void *image, size_t bytes);
#ifdef __cplusplus
}
#endif
#endif
