/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
/* Minimal definitions extracted/adapted from Qualcomm KGSL Linux UAPI.
 * Copyright (c) 2018-2021, The Linux Foundation. All rights reserved.
 * Copyright (c) 2022 Qualcomm Innovation Center, Inc. All rights reserved.
 * Original full UAPI: Pipetto-crypto/libadrenotools src/hook/kgsl.h
 * NOTE: using the complete kernel-matching kgsl.h instead is also valid.
 */
#ifndef KGSL_UAPI_MIN_H
#define KGSL_UAPI_MIN_H
#include <linux/ioctl.h>
#include <stddef.h>
#define KGSL_PROP_DEVICE_SHADOW 0x2
#define KGSL_IOC_TYPE 0x09
struct kgsl_shadowprop {
    unsigned long gpuaddr;
    size_t size;
    unsigned int flags;
};
struct kgsl_device_getproperty {
    unsigned int type;
    void *value;
    size_t sizebytes;
};
#define IOCTL_KGSL_DEVICE_GETPROPERTY \
    _IOWR(KGSL_IOC_TYPE, 0x2, struct kgsl_device_getproperty)
#endif
